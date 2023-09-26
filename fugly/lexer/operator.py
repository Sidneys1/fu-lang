from typing import Optional, Union, Self, TYPE_CHECKING

from . import _LOG, Atom, Lex, LexWarning, lex_dataclass, _SCOPE, StaticType
from ..stream import QuietStreamExpectError
from ..tokenizer import ImmutableTokenStream, SourceLocation, Token, TokenStream, TokenType

if TYPE_CHECKING:
    from . import Type_

PREFIX_BINDING_POWER: dict[str, tuple[None, int]] = {
    '-': (None, 10),
    '!': (None, 10),
}
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


@lex_dataclass
class Operator(Lex):
    """Add: Atom '+' Atom;"""
    OPERATORS = (TokenType.Operator, TokenType.Comma, TokenType.Equals, TokenType.Dot, TokenType.LParen,
                 TokenType.LBracket)
    lhs: Union['Atom', 'Operator']
    rhs: Union['Atom', 'Operator', None]
    oper: 'Token'

    def _s_expr(self) -> tuple[str, list[Self]]:
        match self.oper.type:
            case TokenType.LParen:
                oper = 'call'
            case TokenType.LBracket:
                oper = 'index'
            case _:
                oper = self.oper.value

        if self.lhs is None:
            rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
            return "oper", [oper, rhs]

        lhs = self.lhs.value if isinstance(self.lhs, Atom) else self.lhs
        if self.rhs is None:
            return "oper", [oper, lhs]
        rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
        return f"oper", [oper, lhs, rhs]

    def __str__(self) -> str:
        match self.oper.type:
            case TokenType.Dot:
                return f"{self.lhs}.{self.rhs}"
            case TokenType.LParen:
                return f"{self.lhs}({self.rhs or ''})"
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
        lhs: Atom | Operator | None

        if not stream.eof and stream.peek().type == TokenType.Operator:
            # Prefix operator
            oper = stream.pop()
            _LOG.debug("%sPrefix is %s", '| ' * stream.depth, oper.value)
            _, r_bp = PREFIX_BINDING_POWER[oper.value]
            # TODO
            if (lhs := cls.try_lex(stream, r_bp)) is None:
                return
            lhs = cls(None, lhs, oper, location=SourceLocation.from_to(oper.location, lhs.location))
        elif (lhs := Atom.try_lex(stream)) is None:
            _LOG.warn("%sLeft-hand side was not an Atom", 'x ' * stream.depth)
            return

        while True:
            oper = stream.peek()
            if oper is None:
                print("no oper")
                break
            _LOG.debug("Oper is %r", oper)
            if not any(oper.type == o for o in cls.OPERATORS):
                break
            postfix = POSTFIX_BINDING_POWER.get(oper.value)
            if postfix is not None:
                l_bp, _ = postfix
                if l_bp < min_bp:
                    print("oper not strong enough")
                    break
                stream.pop()
                match oper.type:
                    case TokenType.LParen:
                        rhs = None
                        if (tok := stream.peek()) is not None and tok.type != TokenType.RParen:
                            rhs = cls.try_lex(stream, 0)
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
                print("oper not strong enough")
                break
            stream.pop()
            if (rhs := cls.try_lex(stream, r_bp)) is None:
                print("rhs none")
                break
            lhs = cls(lhs, rhs, oper, location=SourceLocation.from_to(lhs.location, rhs.location))

        return lhs

    def resolve_type(self) -> Optional['Type_']:
        from . import Type_, ParamList
        scope = _SCOPE.get()
        assert (scope is not None)
        match self.oper:
            case Token(type=TokenType.Operator, value='!'):
                # TODO: don't assume we're going to blindly do things here...
                return self.rhs.resolve_type()
            case Token(type=TokenType.LParen):
                lhs_type = self.lhs.resolve_type()
                print(f"calling on {lhs_type}")
                if isinstance(lhs_type, Type_):
                    if not lhs_type.mods:
                        print('UGH')
                        return
                    if not isinstance(lhs_type.mods[-1], ParamList):
                        print('UGH')
                        return
                    return lhs_type.ident.resolve_type()
                assert isinstance(lhs_type, StaticType)
                # if not lhs_type.callable:
                #     return lhs_type.
            case Token(type=TokenType.Dot):
                lhs_type = self.lhs.resolve_type()
                while isinstance(lhs_type, Type_):
                    # Dissolve to a StaticType
                    lhs_type = lhs_type.ident.resolve_type()
                assert isinstance(lhs_type, StaticType)
                with scope.merge(lhs_type.members) as scope:
                    return self.rhs.resolve_type()
            case _:
                raise NotImplementedError(f"`Operator` {self.oper} has not implemented `resolve_type` (in {__file__})")

    def check(self):
        _LOG.debug("Checking operator")
        if self.oper.type == TokenType.Dot:
            from . import Type_
            lhs_type = self.lhs.resolve_type()
            # print(f"lhs: {lhs_type!r}")
            if isinstance(lhs_type, Type_):
                lhs_type = lhs_type.ident.resolve_type()
                # print(f"In Type_: {lhs_type!r}")
                # input()
            scope = _SCOPE.get()
            assert (scope is not None)
            # print('???', lhs_type.members)
            with scope.merge(lhs_type.members) as scope:
                yield from self.lhs.check()
                yield from self.rhs.check()
                ...
            return
        if self.oper.type == TokenType.LParen:
            from . import Type_
            rhs_type = self.rhs.resolve_type()
            print(f"rhs: {rhs_type!r}")
            if isinstance(rhs_type, Type_):
                rhs_type = rhs_type.ident.resolve_type()
                print(f"In Type_: {rhs_type!r}")
                input()
            scope = _SCOPE.get()
            assert (scope is not None)
            print('???', self.lhs.resolve_type(), rhs_type)

        if self.lhs:
            _LOG.debug("Checking %r", self.lhs)
            yield from self.lhs.check()
        if self.rhs is not None:
            _LOG.debug("Checking %r", self.rhs)
            yield from self.rhs.check()
