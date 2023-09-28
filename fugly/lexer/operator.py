from typing import Optional, Union, Self, TYPE_CHECKING

from . import _LOG, Atom, Lex, LexWarning, lex_dataclass  #, _SCOPE, StaticType, CompilerNotice
from ..stream import QuietStreamExpectError
from ..tokenizer import ImmutableTokenStream, SourceLocation, Token, TokenStream, TokenType

if TYPE_CHECKING:
    from . import Type_, ExpList

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
    OPERATORS = (TokenType.Operator, TokenType.Dot, TokenType.LParen, TokenType.LBracket)
    lhs: Union['Atom', 'Operator']
    rhs: Union['Atom', 'Operator', 'ExpList', None]
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
                print("oper not strong enough")
                break
            stream.pop()
            if (rhs := cls.try_lex(stream, r_bp)) is None:
                print("rhs none")
                break
            lhs = cls(lhs, rhs, oper, location=SourceLocation.from_to(lhs.location, rhs.location))

        return lhs

    """
    def resolve_type(self) -> Optional['StaticType']:
        from . import Type_, ParamList
        scope = _SCOPE.get()
        assert (scope is not None)
        match self.oper:
            case Token(type=TokenType.Operator, value='!'):
                # TODO: don't assume we're going to blindly do things here...
                return self.rhs.resolve_type()

            case Token(type=TokenType.LParen):
                lhs_type = self.lhs.resolve_type()
                assert isinstance(lhs_type, StaticType)
                return lhs_type.evals_to
            case Token(type=TokenType.Dot):
                lhs_type = self.lhs.resolve_type()
                _LOG.debug(f"Resolved lhs ({self.lhs}) to {lhs_type}")
                assert isinstance(lhs_type, StaticType)
                with scope.merge(lhs_type.members) as scope:
                    ret = self.rhs.resolve_type()
                    if ret is None:
                        raise CompilerNotice("Error", f"Could not find `{self.rhs}` in type `{lhs_type.name}`.",
                                             self.rhs.location)
                    if ret.callable and ret.callable[0] != lhs_type:
                        raise CompilerNotice(
                            "Error", f"Callable `{ret.name}` does not take `{lhs_type.name}` as its first parameter.",
                            ret.defined_at)

                    return ret.bind()
            case _:
                raise NotImplementedError(f"`Operator` {self.oper} has not implemented `resolve_type` (in {__file__})")

    def _check_call(self):
        from . import ExpList, CompileTimeSurrogate
        try:
            scope = _SCOPE.get()
            assert (scope is not None)
            lhs_type = self.lhs.resolve_type()
            assert lhs_type is not None
            if not lhs_type.callable:
                raise CompilerNotice('Error', f'`{self.lhs}` is not callable', self.location)

            if self.rhs is None and len(lhs_type.callable) != 0:
                raise CompilerNotice(
                    'Error',
                    f"`{self.lhs}` is not callable with no parameters (takes `{'`, `'.join(x.name for x in lhs_type.callable)}`).",
                    self.location)

            assert isinstance(self.rhs, ExpList)
            lhs_count = len(lhs_type.callable)
            rhs_count = len(self.rhs.values)
            if rhs_count != lhs_count:
                raise CompilerNotice('Error', f"`{self.lhs}` expects {lhs_count:,} parameters, got {rhs_count:,}",
                                     self.location)
            for i, (l, r) in enumerate(zip(lhs_type.callable, self.rhs.values)):
                rt = r.resolve_type()
                if l != rt:
                    yield CompilerNotice(
                        'Error', f"Parameter #{i + 1:,} to `{self.lhs}` is expected to be `{l.name}`, not `{rt.name}`.",
                        r.location)
        except CompilerNotice as ex:
            yield ex

    def check(self):
        _LOG.debug("Checking operator")
        if self.oper.type == TokenType.Dot:
            from . import Type_
            lhs_type = self.lhs.resolve_type()
            if isinstance(lhs_type, Type_):
                lhs_type = lhs_type.ident.resolve_type()
            scope = _SCOPE.get()
            assert (scope is not None)
            with scope.merge(lhs_type.members) as scope:
                yield from self.lhs.check()
                yield from self.rhs.check()
                ...
            return
        if self.oper.type == TokenType.LParen:
            yield from self._check_call()

        if self.lhs:
            _LOG.debug("Checking %r", self.lhs)
            yield from self.lhs.check()
        if self.rhs is not None:
            _LOG.debug("Checking %r", self.rhs)
            yield from self.rhs.check()
    """
