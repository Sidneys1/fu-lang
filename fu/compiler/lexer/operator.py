from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterable, Optional, Union, cast

from ..stream import QuietStreamExpectError
from ..tokenizer import SourceLocation, Token, TokenType

from . import _LOG, ImmutableTokenStream, Lex, LexWarning, TokenStream

if TYPE_CHECKING:
    from . import Atom, ExpList, Identifier

PREFIX_BINDING_POWER: dict[str, tuple[None, int]] = {'-': (None, 10), '!': (None, 10), '.': (None, 14)}
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

    def _s_expr(self) -> tuple[str, list[Lex]]:
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
            assert rhs is not None
            return oper, [rhs]

        lhs = self.lhs.value if isinstance(self.lhs, Atom) else self.lhs
        if self.rhs is None:
            return oper, [lhs]
        rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
        return oper, [lhs, rhs]

    def to_code(self) -> Iterable[str]:
        match self.oper.type:
            case TokenType.Dot:
                assert self.lhs is not None and self.rhs is not None
                yield from self.lhs.to_code()
                yield '.'
                yield from self.rhs.to_code()
                return
            case TokenType.LParen:
                assert self.lhs is not None and self.rhs is not None
                yield from self.lhs.to_code()
                yield '('
                yield from self.rhs.to_code()
                yield ')'
                return
            case TokenType.LBracket:
                assert self.lhs is not None and self.rhs is not None
                yield from self.lhs.to_code()
                yield '['
                yield from self.rhs.to_code()
                yield ']'
                return
        if self.lhs is None:
            assert self.rhs is not None
            yield self.oper.value
            yield from self.rhs.to_code()
        elif self.rhs is None:
            assert self.lhs is not None
            yield from self.lhs.to_code()
            yield self.oper.value
        else:
            yield from self.lhs.to_code()
            yield f' {self.oper.value} '
            yield from self.rhs.to_code()

    def __str__(self) -> str:
        match self.lhs, self.oper.type, self.rhs:
            case None, TokenType.Dot, _:
                return f"<this>.{self.rhs}"
            case _, TokenType.Dot, _:
                return f"{self.lhs}.{self.rhs}"
            case _, TokenType.LParen, _:
                return f"{self.lhs}({self.rhs})"
            case _, TokenType.LBracket, _:
                return f"{self.lhs}[{self.rhs}]"
            case None, _, _:
                return f"{self.oper.value}{self.rhs}"
            case _, _, None:
                return f"{self.lhs}{self.oper.value}"
            case _, _, _:
                return f"{self.lhs} {self.oper.value} {self.rhs}"
        raise NotImplementedError()

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
    def try_lex(cls, istream: ImmutableTokenStream, min_bp=0) -> Optional['Lex']:  # type: ignore[override]
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
        raise NotImplementedError()

    @classmethod
    def _try_lex(cls, stream: TokenStream, min_bp=0) -> Lex | None:
        from .atom import Atom
        lhs: Atom | Operator | None
        raw: list[Lex | Token] = []
        if not stream.eof and stream.peek().type in (TokenType.Operator, TokenType.Dot):
            # Prefix operator
            oper = stream.pop()
            raw.append(oper)
            assert oper is not None
            _LOG.debug("%sPrefix is %s", '| ' * stream.depth, oper.value)
            _, r_bp = PREFIX_BINDING_POWER[oper.value]
            # TODO
            if (lhs := cast(Atom | Operator | None, Operator.try_lex(stream, r_bp))) is None:
                return None
            from .lexed_literal import LexedLiteral
            if isinstance(lhs, LexedLiteral
                          ) and lhs.type == TokenType.Number and oper.type == TokenType.Operator and oper.value == '-':
                lhs = replace(lhs, value='-' + lhs.value, location=SourceLocation.from_to(oper.location, lhs.location))
            else:
                lhs = Operator(raw, None, lhs, oper, location=SourceLocation.from_to(oper.location, lhs.location))
            raw = [lhs]
        elif (lhs := Atom.try_lex(stream)) is None:
            _LOG.warn("%sLeft-hand side was not an Atom", 'x ' * stream.depth)
            return None

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
                raw.append(stream.pop())
                match oper.type:
                    case TokenType.LParen:
                        from . import ExpList
                        rhs = None
                        if (tok := stream.peek()) is not None and tok.type != TokenType.RParen:
                            rhs = ExpList.try_lex(stream)
                        raw.append(rhs)
                        raw.append(stream.expect(TokenType.RParen))
                        lhs = Operator(raw,
                                       lhs,
                                       rhs,
                                       oper,
                                       location=SourceLocation.from_to(raw[0].location, raw[-1].location))
                        raw = [lhs]
                    case TokenType.LBracket:
                        rhs = None
                        if (tok := stream.peek()) is not None and tok.type != TokenType.RBracket:
                            rhs = Operator.try_lex(stream, 0)
                        raw.append(rhs)
                        raw.append(stream.expect(TokenType.RBracket))
                        lhs = Operator(raw,
                                       lhs,
                                       rhs,
                                       oper,
                                       location=SourceLocation.from_to(raw[0].location, raw[-1].location))
                        raw = [lhs]
                    case _:
                        lhs = Operator(raw,
                                       lhs,
                                       None,
                                       oper,
                                       location=SourceLocation.from_to(raw[0].location, raw[-1].location))
                        raw = [lhs]
                continue
            l_bp, r_bp = INFIX_BINDING_POWER[oper.value]
            if l_bp < min_bp:
                # print("oper not strong enough")
                break
            raw.append(stream.pop())
            if (rhs := Operator.try_lex(stream, r_bp)) is None:
                # print("rhs none")
                break
            raw.append(rhs)
            lhs = Operator(raw, lhs, rhs, oper, location=SourceLocation.from_to(raw[0].location, raw[-1].location))
            raw = [lhs]
        return lhs
