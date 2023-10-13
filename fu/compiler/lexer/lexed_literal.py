from dataclasses import dataclass

from . import Lex
from ..tokenizer import TokenType


@dataclass(repr=False, slots=True, frozen=True)
class LexedLiteral(Lex):
    value: str
    type: TokenType

    def __str__(self) -> str:
        if self.type == TokenType.String:
            return f'"{self.value}"'
        return self.value

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return str(self), []

    def to_value(self) -> int | float | str | bool:
        match self.type:
            case TokenType.Number:
                return float(self.value) if '.' in self.value else int(self.value)
            case TokenType.String:
                return self.value
            case _:
                raise NotImplementedError()
