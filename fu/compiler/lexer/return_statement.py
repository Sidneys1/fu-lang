from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .. import SourceLocation, TokenStream
from ..tokenizer import TokenType

from . import Lex, _tab, Expression


@dataclass(repr=False, slots=True, frozen=True)
class ReturnStatement(Lex):
    """ReturnStatement: 'return' Expression;"""
    value: Optional['Expression']

    def __str__(self) -> str:
        if self.value is None:
            return f"{_tab()}return;\n"
        return f"{_tab()}return {self.value};\n"

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return "return", [] if self.value is None else [self.value]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        start = stream.expect(TokenType.ReturnKeyword, quiet=True).location
        value = None
        try:
            value = Expression.try_lex(stream)
        except Exception as ex:
            pass
        end = stream.expect(TokenType.Semicolon).location
        return cls(value, location=SourceLocation.from_to(start, end))

    def check(self):
        _LOG.debug("checking returnstatement")
        yield from self.value.check()
