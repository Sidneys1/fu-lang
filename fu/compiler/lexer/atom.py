from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Union

from .. import SourceLocation, TokenStream
from ..tokenizer import Token, TokenType
from . import Identifier, Lex, LexedLiteral, LexError

if TYPE_CHECKING:
    from . import Expression


@dataclass(repr=False, slots=True, frozen=True)
class Atom(Lex):
    """Atom: Literal | Identifier | '(' Expression ')'"""
    value: Union[LexedLiteral, Identifier, 'Expression']

    def to_code(self) -> Iterable[str]:
        yield '('
        yield from self.value.to_code()
        yield ')'

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        from . import Expression
        if (x := stream.peek()) is not None and x.type == TokenType.LParen:
            raw: list[Lex | Token] = []
            raw.append(stream.pop())
            if (body := Expression.try_lex(stream)) is None:
                raise LexError("Expected `Expression`.")
            raw.append(body)
            raw.append(stream.expect(TokenType.RParen))
            return Atom(raw, body, location=SourceLocation.from_to(raw[0].location, raw[-1].location))

        if not stream.eof and stream.peek().type in (TokenType.String, TokenType.Number, TokenType.TrueKeyword, TokenType.FalseKeyword):
            tok = stream.pop()
            return LexedLiteral([tok], tok.value, tok.type, location=tok.location)

        return Identifier.try_lex(stream)
