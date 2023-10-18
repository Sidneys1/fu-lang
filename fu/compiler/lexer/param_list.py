from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from .. import SourceLocation, TokenStream
from ..tokenizer import TokenType

from . import Lex, LexError

if TYPE_CHECKING:
    from . import Identity, Type_


@dataclass(repr=False, slots=True, frozen=True)
class ParamList(Lex):
    """ParamList: '(' Identity [',' Identity[...]] ')';"""
    params: list[Union['Identity', 'Type_']]

    def __str__(self) -> str:
        inner = ', '.join(str(x) for x in self.params)
        return f"({inner})"

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.params)
        return f"Paramlist<{inner}>"

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return 'callable', list(self.params)

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        from . import Identity, Type_
        start = stream.expect(TokenType.LParen, quiet=True).location

        if (tok := stream.peek()) is not None and tok.type == TokenType.RParen:
            end = stream.expect(TokenType.RParen).location
            return cls([], location=SourceLocation.from_to(start, end))

        params: list[Identity | Type_] = []
        while True:
            v: Identity | Type_ | None
            if (v := Identity.try_lex(stream)) is None and (v := Type_.try_lex(stream)) is None:
                raise LexError("Exected `Identity` or `Type_`!")
            params.append(v)
            if (tok := stream.peek()) is not None and tok.type != TokenType.Comma:
                break
            stream.pop()
        end = stream.expect(TokenType.RParen).location
        return cls(params, location=SourceLocation.from_to(start, end))
