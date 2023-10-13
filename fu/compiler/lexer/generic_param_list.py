from dataclasses import dataclass

from .. import TokenStream
from ..tokenizer import SourceLocation, TokenType

from . import Lex, LexError, Identifier


@dataclass(repr=False, slots=True, frozen=True)
class GenericParamList(Lex):
    """GenericParamList: '<' Identifier [',' Identifier[...]] '>';"""
    params: list[Identifier]

    def __str__(self) -> str:
        inner = ', '.join(str(x) for x in self.params)
        return f"<{inner}>"

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.params)
        return f"GenericParamList<{inner}>"

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return 'generics', self.params

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        start = stream.expect(TokenType.LessThan, quiet=True).location

        if (tok := stream.peek()) is not None and tok.type == TokenType.GreaterThan:
            end = stream.expect(TokenType.GreaterThan).location
            return cls([], location=SourceLocation.from_to(start, end))

        params: list[Identifier] = []
        while True:
            if (v := Identifier.try_lex(stream)) is None:
                raise LexError("Exected `Identifier`!")
            params.append(v)
            if (tok := stream.peek()) is not None and tok.type != TokenType.Comma:
                break
            stream.pop()
        end = stream.expect(TokenType.GreaterThan).location
        return cls(params, location=SourceLocation.from_to(start, end))

    def check(self):
        for param in self.params:
            yield from param.check()
