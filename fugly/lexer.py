from abc import ABC
from typing import Iterable, Optional, Union, Self, Literal as Literal_
from logging import getLogger
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass as _dataclass

from fugly.tokenizer import ImmutableTokenStream, TokenStream, Optional

from .tokenizer import TokenType, Token
from .stream import StreamExpectError, QuietStreamExpectError

_LOG = getLogger(__name__)

_FORMATTING_DEPTH: ContextVar[int] = ContextVar('_FORMATTING_DEPTH', default=0)
_TAB = '    '

lex_dataclass = _dataclass(repr=False, slots=True, frozen=True)


def _tab():
    return _TAB * _FORMATTING_DEPTH.get()


@contextmanager
def _indent():
    depth = _FORMATTING_DEPTH.get()
    reset = _FORMATTING_DEPTH.set(depth + 1)
    try:
        yield depth
    finally:
        _FORMATTING_DEPTH.reset(reset)


class LexError(Exception):
    ...


class LexWarning(Warning):
    ...


def parse(istream: ImmutableTokenStream) -> Optional['Document']:
    try:
        return Document.try_lex(istream)
    except LexError as ex:
        _LOG.error("%sFailed to lex `Document`: %s", 'x ' * istream.depth, ex)
    except StreamExpectError as ex:
        expected = ex.expected.__name__ if isinstance(ex.expected, type) else repr(ex.expected)
        _LOG.error("%sFailed to lex `Document`: Expected %s, got %r", 'x ' * istream.depth, expected, ex.got)


class Lex(ABC):
    """Base class for a lexical element."""

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Optional['Lex']:
        _LOG.debug("%sTrying to lex `%s`", '| ' * istream.depth, cls.__name__)
        with istream.clone() as stream:
            try:
                ret = cls._try_lex(stream)
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
    def expect(cls, istream: ImmutableTokenStream) -> 'Lex':
        ret = cls.try_lex(istream)
        if ret is None:
            raise LexError(f"Expected `{cls.__name__}`")
        return ret

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Optional['Lex']:
        ...

    def check(self) -> None:
        ...

    def __repr__(self) -> str:
        value = getattr(self, 'value', None)
        inner = '' if value is None else repr(value)
        return f"{self.__class__.__name__}<{inner}>"

    def unrepr(self, s=None) -> None:
        if s is None:
            s = self.s_expr()
            print(s)
        p = 0
        build = ''
        children = self._s_expr()[1]
        while children:
            for child in children:
                if not isinstance(child, Lex):
                    continue
                r = child.s_expr()
                p = s.find(r, p)
                build += ' ' * (p - len(build))
                build += r
                p += len(r)
            if build != s:
                print(build)
            p = 0
            s = build
            build = ''
            children = [g for c in children if isinstance(c, Lex) for g in c._s_expr()[1]]

    def _s_expr(self) -> tuple[str, list[Self]]:
        if isinstance(value := getattr(self, 'value', None), Lex):
            return self.__class__.__name__.lower(), [value]
        raise NotImplementedError(f"_tree not implemented for {self.__class__.__name__}")

    def s_expr(self) -> str:
        display, children = self._s_expr()
        return '(' + ' '.join(c.s_expr() if isinstance(c, Lex) else str(c) for c in [display] + children) + ')'


class Identifier(Lex):
    """Identifier: Word"""
    value: str

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return self.value

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'identifier', [self.value]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        return cls(stream.expect(TokenType.Word).value)


# class Literal(Lex):
#     """Literal: String | Number;"""
#     value: str

#     def __init__(self, value):
#         self.value = value

#     def __str__(self) -> str:
#         return self.value

#     # def _s_expr(self) -> tuple[str, list[Self]]:
#     #     return self.value, []

#     @classmethod
#     def _try_lex(cls, stream: TokenStream) -> Lex | None:
#         value = stream.pop()
#         if value is None or value.type_ not in (TokenType.String, TokenType.Number):
#             return
#         return cls(value.value)


class Atom(Lex):
    """Atom: Literal | Identifier | '(' Expression ')'"""
    value: Union[str, Identifier, 'Expression']

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return f"({self.value})" if isinstance(self.value, Expression) else self.value

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (x := stream.peek()) is not None and x.type_ == TokenType.LParen:
            stream.pop()
            if (body := Expression.try_lex(stream)) is None:
                raise LexError("Expected `Expression`.")
            stream.expect(TokenType.RParen)
            return cls(body)
        if not stream.eof and stream.peek().type_ in (TokenType.String, TokenType.Number):
            return cls(stream.pop().value)
        return Identifier.try_lex(stream)


PREFIX_BINDING_POWER: dict[str, tuple[None, int]] = {'-': (None, 10)}
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
}
POSTFIX_BINDING_POWER: dict[str, tuple[int, None]] = {'!': (11, None)}


@lex_dataclass
class Operator(Lex):
    """Add: Atom '+' Atom;"""
    OPERATORS = (TokenType.Operator, TokenType.Comma, TokenType.Equals)
    lhs: Union['Atom', 'Operator']
    rhs: Union['Atom', 'Operator', None]
    oper: 'Token'

    def _s_expr(self) -> tuple[str, list[Self]]:
        if self.lhs is None:
            rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
            return "oper", [self.oper.value, rhs]

        lhs = self.lhs.value if isinstance(self.lhs, Atom) else self.lhs
        if self.rhs is None:
            return "oper", [self.oper.value, lhs]
        rhs = self.rhs.value if isinstance(self.rhs, Atom) else self.rhs
        return f"oper", [self.oper.value, lhs, rhs]

    def __str__(self) -> str:
        if self.lhs is None:
            return f"{self.oper.value}{self.rhs}"
        if self.rhs is None:
            return f"{self.lhs}{self.oper.value}"
        return f"{self.lhs} {self.oper.value} {self.rhs}"

    def __repr__(self) -> str:
        if self.lhs is None:
            return f"Operator<{self.oper.value}{self.rhs!r}>"
        if self.rhs is None:
            return f"Operator<{self.lhs!r}{self.oper.value}>"
        return f"Operator<{self.lhs!r}{self.oper.value}{self.rhs!r}>"

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

        if not stream.eof and stream.peek().type_ == TokenType.Operator:
            # Prefix operator
            oper = stream.pop()
            _LOG.debug("%sPrefix is %s", '| ' * stream.depth, oper.value)
            _, r_bp = PREFIX_BINDING_POWER[oper.value]
            # TODO
            if (lhs := cls.try_lex(stream, r_bp)) is None:
                return
            lhs = cls(None, lhs, oper)
        elif (lhs := Atom.try_lex(stream)) is None:
            _LOG.warn("%sLeft-hand side was not an Atom", 'x ' * stream.depth)
            return

        while True:
            oper = stream.peek()
            if oper is None:
                print("no oper")
                break
            _LOG.debug("Oper is %r", oper)
            if not any(oper.type_ == o for o in cls.OPERATORS):
                print("oper not valid")
                break
            postfix = POSTFIX_BINDING_POWER.get(oper.value)
            if postfix is not None:
                l_bp, _ = postfix
                if l_bp < min_bp:
                    print("oper not strong enough")
                    break
                stream.pop()
                lhs = cls(lhs, None, oper)
                continue
            l_bp, r_bp = INFIX_BINDING_POWER[oper.value]
            if l_bp < min_bp:
                print("oper not strong enough")
                break
            stream.pop()
            if (rhs := cls.try_lex(stream, r_bp)) is None:
                print("rhs none")
                break
            lhs = cls(lhs, rhs, oper)

        return lhs

    def check(self):
        if self.lhs:
            self.lhs.check()
        if self.rhs is not None:
            self.rhs.check()


@lex_dataclass
class Expression(Lex):
    """Expression := Add | Identifier | Literal;"""
    value: Union[Operator, 'Atom']

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Expression<{self.value!r}>"

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Operator, Atom]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        for t in cls.allowed:
            if (ret := t.try_lex(stream)) is not None:
                return cls(ret)

    def check(self):
        self.value.check()


@lex_dataclass
class ReturnStatement(Lex):
    """ReturnStatement: 'return' Expression;"""
    value: 'Expression'

    def __str__(self) -> str:
        return f"{_tab()}return {self.value};\n"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(TokenType.ReturnKeyword, quiet=True)
        value = Expression.try_lex(stream)
        stream.expect(TokenType.Semicolon)
        return cls(value)

    def check(self):
        self.value.check()


@lex_dataclass
class ParamList(Lex):
    """ParamList: '(' Identity [',' Identity[...]] ')';"""
    params: list['Identity']

    def __str__(self) -> str:
        inner = ', '.join(str(x) for x in self.params)
        return f"({inner})"

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.params)
        return f"Paramlist<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'params', self.params

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(TokenType.LParen, quiet=True)

        if stream.peek().type_ == TokenType.RParen:
            stream.pop()
            return cls([])

        if (start := Identity.try_lex(stream)) is None:
            raise LexError("Expected Identity.")

        params = [start]
        while stream.peek().type_ == TokenType.Comma:
            stream.pop()
            if (next := Identity.try_lex(stream)) is None:
                raise LexError("Expected Identity.")
            params.append(next)

        stream.expect(TokenType.RParen)
        return cls(params)

    def check(self):
        for param in self.params:
            param.check()


@lex_dataclass
class ArrayDef(Lex):
    """ArrayDef: '[' [Number] ']';"""
    size: Token | None

    def __str__(self) -> str:
        if self.size is not None:
            return f"[{self.size.value}]"
        return "[]"

    def __repr__(self) -> str:
        return str(self)

    def _s_expr(self) -> tuple[str, list[Self]]:
        return f"is-array", [self.size.value] if self.size else []

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(TokenType.LBracket, quiet=True)
        size = None
        if stream.peek().type_ == TokenType.Number:
            size = stream.pop()
        stream.expect(TokenType.RBracket)
        return cls(size)

    def check(self):
        if self.size and '.' in self.size.value:
            _LOG.error("Array sizes cannot be decimals.")


@lex_dataclass
class Type_(Lex):
    """Type_: Identifier [ ArrayDef | ParamList ]"""

    ident: Identifier
    mods: list[ParamList | ArrayDef]

    def __str__(self) -> str:
        if not self.mods:
            return self.ident.value
        mods = ''.join(str(m) for m in self.mods)
        return f"{self.ident}{mods}"

    def __repr__(self) -> str:
        mods = ''.join(repr(m) for m in self.mods) if self.mods else ''
        return f"Type_<{self.ident.value}{mods}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "type", [self.ident] + self.mods

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (ident := Identifier.try_lex(stream)) is None:
            return
        mods = []
        while (mod := (ParamList.try_lex(stream) or ArrayDef.try_lex(stream))) is not None:
            mods.append(mod)
        return cls(ident, mods)

    def check(self):
        self.ident.check()
        for mod in self.mods:
            mod.check()


@lex_dataclass
class Identity(Lex):
    """Identity: Identifier ':' ('namespace' | Type_);"""
    lhs: Identifier
    rhs: Union[Literal_['namespace'], Type_]

    def __str__(self) -> str:
        if isinstance(self.rhs, Token):
            return str(self.lhs) + ": namespace"
        return f"{self.lhs}: {self.rhs}"

    def __repr__(self) -> str:
        return f"Identity<{self.lhs!r}, {self.rhs!r}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return f"identity", [self.lhs, self.rhs]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (lhs := Identifier.try_lex(stream)) is None:
            return
        stream.expect(TokenType.Colon)

        if stream.peek().type_ == TokenType.NamespaceKeyword:
            rhs = 'namespace'
            stream.pop()
        elif (rhs := Type_.try_lex(stream)) is None:
            raise LexError("Expected a `Type_` or 'namespace'.")

        return cls(lhs, rhs)

    def check(self) -> None:
        self.lhs.check()
        if isinstance(self.rhs, Lex):
            self.rhs.check()


@lex_dataclass
class Declaration(Lex):
    """Declaration: Identity [ '=' Expression | Scope ];"""
    identity: Identity
    initial: Union['Scope', 'Expression', None] = None

    def __str__(self) -> str:
        if self.initial is not None:
            return f"{self.identity} = {self.initial}"
        return f"{self.identity}"

    def __repr__(self) -> str:
        after = '' if self.initial is None else f'={self.initial!r}'
        return f"Declaration<{self.identity!r}{after}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'declaration', [self.identity] if self.initial is None else [self.identity, self.initial]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (identity := Identity.try_lex(stream)) is None:
            return

        if stream.peek().type_ != TokenType.Equals:
            return cls(identity)

        stream.pop()

        val = Scope.try_lex(stream) or Expression.try_lex(stream)
        if val is None:
            raise LexError("Expected a `Scope` or `Expression`!")
        return cls(identity, val)

    def check(self) -> None:
        self.identity.check()
        if self.initial is not None:
            self.initial.check()


@lex_dataclass
class Statement(Lex):
    """Statement: Declaration | Expression;"""
    value: Union['Expression', 'Declaration']

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Declaration, Expression]

    def __str__(self) -> str:
        return f'{_tab()}{self.value};\n'

    def __repr__(self) -> str:
        return f"Statement<{self.value!r}>"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        res = None
        for t in cls.allowed:
            if (res := t.try_lex(stream)) is not None:
                break
        stream.expect(TokenType.Semicolon)
        return cls(res)

    def check(self) -> None:
        self.value.check()


@lex_dataclass
class Scope(Lex):
    """Scope: '{' (Statement | ReturnStatement)* '}';"""
    content: list['ReturnStatement', 'Statement']

    def __str__(self) -> str:
        with _indent():
            inner = ''.join(str(x) for x in self.content)
        if not inner:
            return '{ }'
        return '{\n' + inner + _tab() + '}'

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.content)
        return f"Scope<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "scope", self.content

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(TokenType.LBrace, quiet=True)
        ret = []
        while not stream.eof:
            match stream.peek().type_:
                case TokenType.RBrace:
                    stream.pop()
                    return cls(ret)
                case TokenType.ReturnKeyword:
                    ret.append(ReturnStatement.try_lex(stream))
                    continue
                case _:
                    if (res := Statement.try_lex(stream)) is None:
                        raise LexError("Expected `Statement`!")
                    ret.append(res)
                    continue

        stream.expect(TokenType.RBrace)
        return cls(ret)

    def check(self):
        if not self.content:
            _LOG.warn("Empty Scope?")
            return
        last = self.content[-1]
        for statement in self.content:
            statement.check()
            if isinstance(statement, ReturnStatement) and statement is not last:
                _LOG.error("Return statement was not the last statement in scope.")


@lex_dataclass
class Document(Lex):
    """Document: Statement* EOF;"""
    statements: list[Statement]

    @classmethod
    @property
    def allowed(cls) -> list[type[Lex]]:
        return (Statement, )

    def __str__(self) -> str:
        return ''.join(str(s) for s in self.statements)

    def __repr__(self) -> str:
        inner = ', '.join(repr(s) for s in self.statements)
        return f"Document<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'document', self.statements

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        statements: list[Statement] = []
        while (res := Statement.try_lex(stream)):
            statements.append(res)
        if not stream.eof:
            return None
        return cls(statements)

    def check(self) -> None:
        for statement in self.statements:
            statement.check()
