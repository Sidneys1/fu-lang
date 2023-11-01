from dataclasses import replace
from typing import Generator

from ...compiler import CompilerNotice
from ...compiler.lexer import (Atom, Declaration, Document, ExpList, Identifier, Lex, Namespace, Operator,
                               ReturnStatement, Scope, Statement, Token, TokenType, Type_, TypeDeclaration)
from ..lexer.lexed_literal import LexedLiteral


def _optimize(element: Lex) -> Generator[CompilerNotice, None, Lex]:
    match element:
    # case Operator(lhs=None):
    #     # yield CompilerNotice('Info',
    #     #                      f"{type(element.lhs).__name__} {element.oper.value} {type(element.rhs).__name__}",
    #     #                      element.location)
    #     return element
    # case Operator(rhs=None):
    #     yield CompilerNotice('Info',
    #                          f"{type(element.lhs).__name__} {element.oper.value} {type(element.rhs).__name__}",
    #                          element.location)
    #     return element
        case Operator(oper=Token(type=TokenType.Operator)):
            """Infix operator"""
            assert element.rhs is not None and element.lhs is not None

            lhs = yield from _optimize(element.lhs)
            rhs = yield from _optimize(element.rhs)
            match lhs, element.oper.value, rhs:
                case LexedLiteral(type=TokenType.Number), '+', LexedLiteral(type=TokenType.Number):
                    ret = LexedLiteral([],
                                       value=str(lhs.to_value() + rhs.to_value()),
                                       type=TokenType.Number,
                                       location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized addition of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case LexedLiteral(type=TokenType.Number), '-', LexedLiteral(type=TokenType.Number):
                    ret = LexedLiteral([],
                                       value=str(lhs.to_value() - rhs.to_value()),
                                       type=TokenType.Number,
                                       location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized subtraction of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case LexedLiteral(type=TokenType.Number), '*', LexedLiteral(type=TokenType.Number):
                    ret = LexedLiteral([],
                                       value=str(lhs.to_value() * rhs.to_value()),
                                       type=TokenType.Number,
                                       location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized multiplication of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case LexedLiteral(type=TokenType.Number), '/', LexedLiteral(type=TokenType.Number):
                    ret = LexedLiteral([],
                                       value=str(lhs.to_value() / rhs.to_value()),
                                       type=TokenType.Number,
                                       location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized division of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case LexedLiteral(), _, LexedLiteral():
                    yield CompilerNotice(
                        'Info',
                        f"Not sure how to optimize an infix operator between two literals: {element.lhs}{element.oper.value}{element.rhs}",
                        element.location)
                    # yield CompilerNotice('Info', f"oooh", element.location)
            if lhs != element.lhs or rhs != element.rhs:
                return replace(element, lhs=lhs, rhs=rhs)
            return element
        case Atom() | Statement():
            new_value = yield from _optimize(element.value)
            if new_value != element.value:
                return replace(element, value=new_value)
        case ExpList():
            if not element.values:
                return element
            different = False
            new_values = []
            for e in element.values:
                new_e = yield from _optimize(e)
                if new_e != e:
                    different = True
                    new_values.append(new_e)
                else:
                    new_values.append(e)
            if different:
                return replace(element, values=new_values)
        case ReturnStatement():
            if element.value is None:
                return element
            new_value = yield from _optimize(element.value)
            if new_value != element.value:
                return replace(element, value=new_value)
        case Scope():
            if not element.content:
                return element
            different = False
            new_content = []
            for e in element.content:
                new_e = yield from _optimize(e)
                if new_e != e:
                    different = True
                    new_content.append(new_e)
                else:
                    new_content.append(e)
            if different:
                return replace(element, content=new_content)
        case Declaration():
            if element.initial is None:
                return element
            initial = yield from _optimize(element.initial)
            if initial != element.initial:
                return replace(element, initial=initial)
        case TypeDeclaration():
            if element.definition is None:
                return element
            if isinstance(element.definition, Type_):
                return element
            different = False
            new_defs = []
            for e in element.definition:
                new_e = yield from _optimize(e)
                if new_e != e:
                    different = True
                    new_defs.append(new_e)
                else:
                    new_defs.append(e)
            if different:
                return replace(element, definition=new_defs)
        case Document():
            different = False
            content: list[Declaration | TypeDeclaration | Namespace] = []
            for c in element.content:
                new_c = yield from _optimize(c)
                if new_c is not None and new_c != c:
                    different = True
                    content.append(new_c)
                else:
                    content.append(c)
            if different:
                return replace(element, content=content)
        # case LexedLiteral() | Operator(oper=Token(type=TokenType.Dot)) | Operator(oper=Token(
        #     type=TokenType.Equals)) | Identifier() | Namespace():
        #     """Ignore"""
        # case _:
        #     yield CompilerNotice('Note', f"Don't know how to optimize `{type(element).__name__}`.", element.location)
    return element
