from typing import TYPE_CHECKING, Callable

from ...types import SIZE_TYPE, STR_TYPE, USIZE_TYPE, VOID_TYPE, F32_TYPE, FloatType, IntType, TypeBase
from ...types.integral_types import IntegralType
from .. import CompilerNotice
from ..lexer import ExpList, Identifier, Lex, Operator, ReturnStatement, StaticScope, Token, TokenType, Type_
from ..lexer.lexed_literal import LexedLiteral
from . import _LOG
from .scope import AnalyzerScope
from .static_variable_decl import OverloadedMethodDecl, StaticVariableDecl

if TYPE_CHECKING:
    from ..lexer import Atom


def resolve_type(element: Lex,
                 want: TypeBase | None = None,
                 want_signed: bool = False,
                 warn: Callable[[CompilerNotice], None] | None = None) -> StaticVariableDecl | TypeBase | StaticScope:
    from .static_type import type_from_lex
    if warn is None:

        def x(_: CompilerNotice) -> None:
            pass

        warn = x

    scope = AnalyzerScope.current()

    # _LOG.debug(f"Resolving type of {element!r} in {scope.fqdn}")
    match element:
        case ReturnStatement():
            if element.value is None:
                return VOID_TYPE
            return resolve_type(element.value)
        case Operator(oper=Token(type=TokenType.Dot), lhs=None):
            # prefix dot
            lhs_type = scope.in_scope('this')
            if lhs_type is None:
                raise CompilerNotice(
                    'Error', f"Cannot use `.xyz` syntax, as it is equivalent to `this.xyz` and `this` is not in scope.",
                    element.location)
            lhs_decl = None
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            assert isinstance(
                element.rhs,
                Identifier), f"Expected Identifier on rhs of {element!r}, got `{type(element.rhs).__name__}`"
            ret = lhs_type.members.get(element.rhs.value, None)
            if ret is None:
                raise CompilerNotice('Error',
                                     f"{lhs_type.type.name} has no member {element.rhs.value}.",
                                     location=element.location)
            # input(f"OP DOT against lhs members: \n\n{lhs_decl.type.name}.{element.rhs.value}\n->\n{ret.name}")
            return ret
        case Operator(oper=Token(type=TokenType.Dot)):
            lhs_type = resolve_type(element.lhs)
            lhs_decl = None
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            assert isinstance(element.rhs, Identifier)
            ret = lhs_type.members.get(element.rhs.value, None)
            if ret is None:
                raise CompilerNotice('Error',
                                     f"{lhs_type.name} has no member {element.rhs.value}.",
                                     location=element.location)
            return ret
        case Operator(oper=Token(type=TokenType.LBracket)):
            lhs_type = resolve_type(element.lhs)
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            if not lhs_type.indexable:
                raise CompilerNotice('Error', f"{lhs_type.name} is not array indexable.", location=element.lhs.location)
            return lhs_type.indexable[1]
        case Operator(oper=Token(type=TokenType.LParen)):
            lhs_type = resolve_type(element.lhs)
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            if isinstance(lhs_type, OverloadedMethodDecl):
                if element.rhs is None:
                    rhs_params = tuple()
                else:
                    assert isinstance(element.rhs, ExpList)
                    rhs_params = tuple(resolve_type(v) for v in element.rhs.values)
                return lhs_type.match(rhs_params).type.return_type
            if lhs_type.callable:
                # input(f"`{element}` returns `{lhs_type.callable[1].name}`")
                return lhs_type.callable[1]
            raise CompilerNotice('Error', f"{lhs_type.name} is not callable.", location=element.lhs.location)
        case Operator(oper=Token(type=TokenType.Operator), lhs=None):  # prefix operator
            assert isinstance(element, Operator)
            if element.oper.value == '-' and isinstance(element.rhs,
                                                        LexedLiteral) and element.rhs.type == TokenType.Number:
                raise RuntimeError("This shoudl never happen...")
                return resolve_type(element.rhs, want=want, want_signed=True)

            rhs_type = resolve_type(element.rhs)
            if isinstance(rhs_type, StaticVariableDecl):
                rhs_decl = rhs_type
                rhs_type = rhs_type.type
            match element.oper.value, rhs_type:
            # case '-', Literal(type=TokenType.Number):
            #     ...
                case _:
                    raise NotImplementedError(
                        f"Don't know how to resolve type of prefix operator `{element.oper.value}` on `{type(rhs_type).__name__}`"
                    )
        case Operator(oper=Token(type=TokenType.Operator)):
            if element.lhs is None or element.rhs is None:
                raise NotImplementedError(f"Oops! {element.lhs is None} {element.rhs is None}")

            if isinstance(element.lhs, LexedLiteral) and isinstance(element.rhs, LexedLiteral):
                return resolve_literal_operation(element, want=want, want_signed=want_signed, warn=warn)

            lhs_type = resolve_type(element.lhs)
            rhs_type = resolve_type(element.rhs)
            if isinstance(lhs_type, StaticScope) or isinstance(rhs_type, StaticScope):
                raise CompilerNotice('Error', "Cannot operate on scopes!", element.location)

            # lhs_decl: StaticVariableDecl | None = None
            if isinstance(lhs_type, StaticVariableDecl):
                # lhs_decl = lhs_type
                lhs_type = lhs_type.type
            # rhs_decl: StaticVariableDecl | None = None
            if isinstance(rhs_type, StaticVariableDecl):
                # rhs_decl = rhs_type
                rhs_type = rhs_type.type

            # input(f"\n\n{lhs_type.name} {element.oper.value} {rhs_type.name}")
            match lhs_type, rhs_type:
                case FloatType(), FloatType():
                    assert isinstance(lhs_type, FloatType) and isinstance(rhs_type, FloatType)
                    oper_name = {
                        '+': 'addition',
                        '-': 'subtraction',
                        '*': 'multiplication',
                        '/': 'division'
                    }.get(element.oper.value, element.oper.value)
                    if lhs_type.size != rhs_type.size:
                        warn(
                            CompilerNotice(
                                'Warning',
                                f"Performing `{oper_name}` between floating point types of different size can result in inforation loss.",
                                element.location))
                    return max((x for x in (lhs_type, rhs_type)), key=lambda x: x.size or 0)
                case IntType(), IntType():
                    assert isinstance(lhs_type, IntType) and isinstance(rhs_type, IntType)
                    oper_name = {
                        '+': 'addition',
                        '-': 'subtraction',
                        '*': 'multiplication',
                        '/': 'division'
                    }.get(element.oper.value, element.oper.value)
                    if lhs_type.signed != rhs_type.signed or lhs_type.size != rhs_type.size:
                        warn(
                            CompilerNotice(
                                'Warning',
                                f"Performing `{oper_name}` between numeric types of different signedness or size can result in inforation loss.",
                                element.location))
                    return max((x for x in (lhs_type, rhs_type)), key=lambda x: x.size or 0)
                case _, _:
                    raise NotImplementedError()
            raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.Equals)):
            return VOID_TYPE
        case Identifier():
            ret = scope.in_scope(element.value)
            if ret is None:
                raise CompilerNotice('Error',
                                     f"Identifier `{element.value}` is not defined.",
                                     location=element.location)
            return ret
        case Operator():
            raise CompilerNotice('Note', f"Type resolution for Operator `{element.oper}` is not implemented!",
                                 element.location)
        case LexedLiteral():
            match element.type:
                case TokenType.String:
                    return STR_TYPE
                case TokenType.Number:
                    # TODO: determine actual type of literal
                    if element.value.endswith('f'):
                        val = float(element.value[:-1])
                        if want is not None and isinstance(want, IntegralType) and want.could_hold_value(int(val)):
                            return want.as_const()
                        return F32_TYPE.as_const()
                    if 'f' in element.value or '.' in element.value:
                        raise NotImplementedError()
                    if 'i' in element.value:
                        raise NotImplementedError()
                    # Bare Integer
                    if want is not None and isinstance(want, IntegralType) and want.could_hold_value(element.value):
                        return want.as_const()
                    return SIZE_TYPE.as_const() if want_signed or element.value[0] == '-' else USIZE_TYPE.as_const()
                case _:
                    raise NotImplementedError()
        case Type_():
            return type_from_lex(element, scope)
        case _:
            raise CompilerNotice('Note', f"Type resolution for `{type(element).__name__}` is not implemented!",
                                 element.location)


def resolve_owning_type(element: Lex) -> tuple[StaticVariableDecl, StaticVariableDecl]:
    _LOG.debug(f"Trying to find owning type of `{element}`.")
    scope = AnalyzerScope.current()
    match element:
        case Operator(oper=Token(type=TokenType.Dot), rhs=Identifier()):
            _LOG.debug(f"Trying to find `{element.rhs}` in `{element.lhs}`.")
            lhs_decl = scope.in_scope('this') if element.lhs is None else resolve_type(element.lhs)
            assert lhs_decl is not None and isinstance(lhs_decl, StaticVariableDecl)
            # print(f"\n\n{scope.members.keys()}\n")
            # input(f"lhs_type is {lhs_decl.type.name}: {lhs_decl.member_decls}")

            member_name = element.rhs.value
            if member_name not in lhs_decl.type.members and member_name not in lhs_decl.member_decls:
                raise CompilerNotice('Error', f"`{lhs_decl.type.name}` does not have a {member_name!r} member.",
                                     element.rhs.location)

            return lhs_decl, lhs_decl.member_decls[member_name]
        case Identifier():
            return None, scope.in_scope(element.value)
        case Operator():
            raise NotImplementedError(f"Don't know how to find owning type of Operator(oper={element.oper.type.name}).")
        case _:
            raise NotImplementedError(f"Don't know how to find owning type of {type(element).__name__}.")


def resolve_literal_operation(
        element: Operator,
        want: TypeBase | None = None,
        want_signed: bool = False,
        warn: Callable[[CompilerNotice], None] | None = None) -> StaticVariableDecl | TypeBase | StaticScope:
    assert isinstance(element.lhs, LexedLiteral) and isinstance(element.rhs, LexedLiteral)

    if element.lhs.type != TokenType.Number or element.rhs.type != TokenType.Number:
        raise NotImplementedError()

    lhs_value = element.lhs.to_value()
    rhs_value = element.rhs.to_value()
    assert isinstance(lhs_value, (int, float)) and isinstance(rhs_value, (int, float))

    match element.oper.value:
        case '+':
            val = lhs_value + rhs_value
        case '-':
            val = lhs_value - rhs_value
        case '*':
            val = lhs_value * rhs_value
        case '/':
            val = lhs_value / rhs_value
        case _:
            raise NotImplementedError()

    if isinstance(val, int):
        if isinstance(want, IntType) and want.could_hold_value(val):
            return want
        return IntType.best_for_value(val, want_signed=want_signed)
    if isinstance(val, float):
        if isinstance(want, FloatType) and want.could_hold_value(val):
            return want
        return FloatType.best_for_value(val)


__all__ = ('resolve_type', 'resolve_owning_type', 'resolve_literal_operation')
