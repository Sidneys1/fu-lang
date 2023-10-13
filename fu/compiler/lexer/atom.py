from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from .. import TokenStream, SourceLocation
from ..tokenizer import TokenType

from . import Lex, Identifier, LexedLiteral, LexError

if TYPE_CHECKING:
    from . import Expression


@dataclass(repr=False, slots=True, frozen=True)
class Atom(Lex):
    """Atom: Literal | Identifier | '(' Expression ')'"""
    value: Union[LexedLiteral, Identifier, 'Expression']

    def __str__(self) -> str:
        return f"({self.value})"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        from . import Expression
        if (x := stream.peek()) is not None and x.type == TokenType.LParen:
            start = stream.pop().location
            if (body := Expression.try_lex(stream)) is None:
                raise LexError("Expected `Expression`.")
            end = stream.expect(TokenType.RParen).location
            return cls(body, location=SourceLocation.from_to(start, end))

        if not stream.eof and stream.peek().type in (TokenType.String, TokenType.Number):
            tok = stream.pop()
            return LexedLiteral(tok.value, tok.type, location=tok.location)

        return Identifier.try_lex(stream)
