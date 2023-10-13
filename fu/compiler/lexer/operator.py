from typing import Optional, Union, Self, TYPE_CHECKING
from dataclasses import replace, dataclass

from . import _LOG, Lex, LexWarning, TokenStream, ImmutableTokenStream
from ..stream import QuietStreamExpectError
from ..tokenizer import SourceLocation, Token, TokenType

if TYPE_CHECKING:
    from . import ExpList, Identifier, Atom

PREFIX_BINDING_POWER: dict[str, tuple[None, int]] = {'-': (None, 10), '!': (None, 10), '.': (None, 10)}
INFIX_BINDING_POWER: dict[str, tuple[int, int]] = {
    ',': (1, 2),
    '=': (3, 4),
    # ...
    '+': (5, 6),
    '-': (5, 6),
    # ...
    '*': (7, 8),
    '/': (7, 8),
    # PREFIX -
    '.': (13, 14),
}
POSTFIX_BINDING_POWER: dict[str, tuple[int, None]] = {
    '(': (11, None),
    '[': (11, None),
}


@dataclass(repr=False, slots=True, frozen=True)
class Operator(Lex):
    """Add: Atom '+' Atom;"""
    OPERATORS = (TokenType.Operator, TokenType.Dot, TokenType.LParen, TokenType.LBracket, TokenType.Equals)
    lhs: Union['Atom', 'Identifier', 'Operator', None]
    rhs: Union['Atom', 'Identifier', 'Operator', 'ExpList', None]
    oper: 'Token'

    def _s_expr(self) -> tuple[str, list[Self]]:
        from .atom import Atom
        match self.oper.type:
            case TokenType.LParen:
                oper = 'call'
            case TokenType.LBracket:
                oper = 'index'
            case _:
                oper = self.oper.value

        if self.lhs is None:
            rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
            return oper, [rhs]

        lhs = self.lhs.value if isinstance(self.lhs, Atom) else self.lhs
        if self.rhs is None:
            return oper, [lhs]
        rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
        return oper, [lhs, rhs]

    def __str__(self) -> str:
        match self.oper.type:
            case TokenType.Dot:
                return f"{self.lhs}.{self.rhs}"
            case TokenType.LParen:
                return f"{self.lhs}{self.rhs or '()'}"
            case TokenType.LBracket:
                return f"{self.lhs}[{self.rhs or ''}]"

        if self.lhs is None:
            return f"{self.oper.value}{self.rhs}"
        if self.rhs is None:
            return f"{self.lhs}{self.oper.value}"
        return f"{self.lhs} {self.oper.value} {self.rhs}"

    def __repr__(self) -> str:
        match self.oper.type:
            case TokenType.LParen:
                oper = 'call'
            case TokenType.LBracket:
                oper = 'index'
            case _:
                oper = self.oper.value
        if self.lhs is None:
            return f"Operator<{oper}{self.rhs!r}>"
        if self.rhs is None:
            return f"Operator<{self.lhs!r}{oper}>"
        return f"Operator<{self.lhs!r}{oper}{self.rhs!r}>"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream, min_bp=0) -> Optional['Lex']:
        _LOG.debug("%sTrying to lex `%s` (min_bp=%d)", '| ' * istream.depth, cls.__name__, min_bp)
        with istream.clone() as stream:
            try:
                ret = cls._try_lex(stream, min_bp)
                if ret is not None:
                    stream.commit()
                    _LOG.debug("%sWas a `%s`!", 'y ' * istream.depth, cls.__name__)
                return ret
            except LexWarning as ex:
                _LOG.warn("%sFailed to lex `%s`: %s", 'x ' * istream.depth, cls.__name__, ex)
            except EOFError as ex:
                _LOG.error("%sFailed to lex `%s`: Reached end of file", 'x ' * istream.depth, cls.__name__)
            except QuietStreamExpectError:
                pass

    @classmethod
    def _try_lex(cls, stream: TokenStream, min_bp=0) -> Lex | None:
        from .atom import Atom
        lhs: Atom | Operator | None

        if not stream.eof and stream.peek().type in (TokenType.Operator, TokenType.Dot):
            # Prefix operator
            oper = stream.pop()
            assert oper is not None
            _LOG.debug("%sPrefix is %s", '| ' * stream.depth, oper.value)
            _, r_bp = PREFIX_BINDING_POWER[oper.value]
            # TODO
            if (lhs := cls.try_lex(stream, r_bp)) is None:
                return
            from .lexed_literal import LexedLiteral
            if isinstance(lhs, LexedLiteral
                          ) and lhs.type == TokenType.Number and oper.type == TokenType.Operator and oper.value == '-':
                lhs = replace(lhs, value='-' + lhs.value, location=SourceLocation.from_to(oper.location, lhs.location))
            else:
                lhs = cls(None, lhs, oper, location=SourceLocation.from_to(oper.location, lhs.location))
        elif (lhs := Atom.try_lex(stream)) is None:
            _LOG.warn("%sLeft-hand side was not an Atom", 'x ' * stream.depth)
            return

        while True:
            oper = stream.peek()
            if oper is None:
                # print("no oper")
                break
            _LOG.debug("Oper is %r", oper)
            if not any(oper.type == o for o in cls.OPERATORS):
                break
            postfix = POSTFIX_BINDING_POWER.get(oper.value)
            if postfix is not None:
                l_bp, _ = postfix
                if l_bp < min_bp:
                    # print("oper not strong enough")
                    break
                stream.pop()
                match oper.type:
                    case TokenType.LParen:
                        from . import ExpList
                        rhs = None
                        if (tok := stream.peek()) is not None and tok.type != TokenType.RParen:
                            rhs = ExpList.try_lex(stream)
                        end = stream.expect(TokenType.RParen)
                        lhs = cls(lhs, rhs, oper, location=SourceLocation.from_to(lhs.location, end.location))
                    case TokenType.LBracket:
                        rhs = None
                        if (tok := stream.peek()) is not None and tok.type != TokenType.RBracket:
                            rhs = cls.try_lex(stream, 0)
                        end = stream.expect(TokenType.RBracket)
                        lhs = cls(lhs, rhs, oper, location=SourceLocation.from_to(lhs.location, end.location))
                    case _:
                        lhs = cls(lhs, None, oper, location=SourceLocation.from_to(lhs.location, oper.location))
                continue
            l_bp, r_bp = INFIX_BINDING_POWER[oper.value]
            if l_bp < min_bp:
                # print("oper not strong enough")
                break
            stream.pop()
            if (rhs := cls.try_lex(stream, r_bp)) is None:
                # print("rhs none")
                break
            lhs = cls(lhs, rhs, oper, location=SourceLocation.from_to(lhs.location, rhs.location))

        return lhs
