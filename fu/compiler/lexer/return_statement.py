from dataclasses import dataclass
from typing import Iterable, Optional

from .. import SourceLocation, TokenStream
from ..tokenizer import Token, TokenType
from . import Expression, Lex, _tab


@dataclass(repr=False, slots=True, frozen=True)
class ReturnStatement(Lex):
    """ReturnStatement: 'return' Expression;"""
    value: Optional['Expression']

    def to_code(self) -> Iterable[str]:
        yield _tab() + 'return'
        if self.value is not None:
            yield ' '
            yield from self.value.to_code()
        yield ';'

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return "return", [] if self.value is None else [self.value]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        raw: list[Lex | Token] = [stream.expect(TokenType.ReturnKeyword, quiet=True)]
        value = None
        try:
            raw.append(value := Expression.try_lex(stream))
        except Exception as ex:
            pass
        raw.append(stream.expect(TokenType.Semicolon))
        return ReturnStatement(raw, value, location=SourceLocation.from_to(raw[0].location, raw[-1].location))
