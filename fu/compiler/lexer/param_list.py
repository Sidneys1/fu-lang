from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Union

from .. import SourceLocation, TokenStream
from ..tokenizer import Token, TokenType
from . import Lex, LexError

if TYPE_CHECKING:
    from . import Identity, Type_


@dataclass(repr=False, slots=True, frozen=True)
class ParamList(Lex):
    """ParamList: '(' Identity [',' Identity[...]] ')';"""
    params: list[Union['Identity', 'Type_']]

    def to_code(self) -> Iterable[str]:
        for x in self.raw:
            if isinstance(x, Lex):
                yield from x.to_code()
            elif x.type == TokenType.BlankLine:
                pass
            else:
                yield x.value
                if x.type == TokenType.Comma:
                    yield ' '

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
        raw: list[Lex | Token] = [stream.expect(TokenType.LParen, quiet=True)]

        if (tok := stream.peek()) is not None and tok.type == TokenType.RParen:
            raw.append(stream.expect(TokenType.RParen))
            return ParamList(raw, [], location=SourceLocation.from_to(raw[0].location, raw[-1].location))

        params: list[Identity | Type_] = []
        while True:
            v: Identity | Type_ | None
            if (v := Identity.try_lex(stream)) is None and (v := Type_.try_lex(stream)) is None:
                raise LexError("Exected `Identity` or `Type_`!")
            raw.append(v)
            params.append(v)
            if (tok := stream.peek()) is not None and tok.type != TokenType.Comma:
                break
            raw.append(stream.pop())
        raw.append(stream.expect(TokenType.RParen))
        return ParamList(raw, params, location=SourceLocation.from_to(raw[0].location, raw[-1].location))
