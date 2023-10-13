from dataclasses import dataclass

from . import Lex, TokenStream, TokenType


@dataclass(repr=False, slots=True, frozen=True)
class Identifier(Lex):
    """Identifier: Word"""
    value: str

    def __str__(self) -> str:
        return self.value

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return f'"{self.value}"', []

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (tok := stream.pop()) is None or tok.type != TokenType.Word:
            return None
        return cls(tok.value, location=tok.location)
