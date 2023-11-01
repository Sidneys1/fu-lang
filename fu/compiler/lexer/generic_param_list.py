from dataclasses import dataclass
from typing import Iterable

from .. import TokenStream
from ..tokenizer import SourceLocation, Token, TokenType
from . import Identifier, Lex, LexError


@dataclass(repr=False, slots=True, frozen=True)
class GenericParamList(Lex):
    """GenericParamList: '<' Identifier [',' Identifier[...]] '>';"""
    params: list[Identifier]

    def to_code(self) -> Iterable[str]:
        for x in self.raw:
            if isinstance(x, Lex):
                yield from x.to_code()
            elif x.type == TokenType.BlankLine:
                # Don't preserve blank lines!
                pass
            else:
                yield x.value
                if x.type == TokenType.Comma:
                    yield ' '

    def __str__(self) -> str:
        inner = ', '.join(str(x) for x in self.params)
        return f"GenericParamList<{inner}>"

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.params)
        return f"GenericParamList<{inner}>"

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return 'generics', self.params

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        raw: list[Lex, Token] = [stream.expect(TokenType.LessThan, quiet=True)]

        if (tok := stream.peek()) is not None and tok.type == TokenType.GreaterThan:
            raw.append(stream.expect(TokenType.GreaterThan))
            return GenericParamList(raw, [], location=SourceLocation.from_to(raw[0].location, raw[-1].location))

        params: list[Identifier] = []
        while True:
            if (v := Identifier.try_lex(stream)) is None:
                raise LexError("Exected `Identifier`!")
            params.append(v)
            raw.append(v)
            if (tok := stream.peek()) is not None and tok.type != TokenType.Comma:
                break
            raw.append(stream.pop())
        raw.append(stream.expect(TokenType.GreaterThan))
        return GenericParamList(raw, params, location=SourceLocation.from_to(raw[0].location, raw[-1].location))
