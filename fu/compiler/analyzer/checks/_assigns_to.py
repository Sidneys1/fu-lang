from typing import Iterator

from ... import CompilerNotice
from ...lexer import Lex, Operator, Statement
from ...tokenizer import Token, TokenType

from .. import CompilerNotice
from ..static_variable_decl import StaticVariableDecl, _decl_of


def _assigns_to(element: Lex) -> Iterator[StaticVariableDecl]:
    match element:
        case Operator(oper=Token(type=TokenType.Equals)):
            assert element.lhs is not None
            yield _decl_of(element.lhs)
        case Statement():
            yield from _assigns_to(element.value)
        case _:
            raise CompilerNotice('Critical', f"Assigns-to checks for {type(element).__name__} are not implemented!",
                                 element.location)
