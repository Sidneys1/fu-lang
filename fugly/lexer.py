from abc import ABC
from typing import Iterable, Optional, Union, Self
from logging import getLogger
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass as _dataclass

from fugly.tokenizer import ImmutableTokenStream, TokenStream, Optional

from .tokenizer import *
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
            s = repr(self)
            print(s)
        p = 0
        build = ''
        children = self._tree()[1]
        while children:
            for child in children:
                r = repr(child)
                p = s.find(r, p)
                # _LOG.debug("%d, %s", p, r)
                build += ' ' * (p - len(build))
                build += r
                p += len(r)
            if build != s:
                print(build)
            p = 0
            s = build
            build = ''
            children = [g for c in children for g in c._tree()[1]]

    def _tree(self) -> tuple[str, list[Self]]:
        if isinstance(value := getattr(self, 'value', None), Lex):
            return self.__class__.__name__, [value]
        raise NotImplementedError(f"_tree not implemented for {self.__class__.__name__}")

    def tree(self, depth: int = 0, draw_depth=True) -> None:
        display, children = self._tree()
        if len(children) == 1:
            print(('| ' * depth) if draw_depth else '', display, ' -> ', sep='', end='')
            children[0].tree(depth + 1, False)
            return
        print(('| ' * depth) if draw_depth else '', display, sep='')
        for child in children:
            child.tree(depth + 1)


class Identifier(Lex):
    """Identifier: Word"""
    value: str

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return self.value

    def _tree(self) -> tuple[str, list[Self]]:
        return f'Identifier<{self.value}>', []

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        return cls(stream.expect(Word).value)


class Literal(Lex):
    """Literal: String | Number;"""
    value: str

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return self.value

    def _tree(self) -> tuple[str, list[Self]]:
        return self.value, []

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        value = stream.pop()
        if not (isinstance(value, String) or isinstance(value, Number)):
            return
        return cls(value.value)


class Atom(Lex):
    """Atom: Literal | Identifier | '(' Expression ')'"""
    value: Union[Literal, Identifier, 'Expression']

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return f"({self.value})" if isinstance(self.value, Expression) else self.value.value

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if isinstance(stream.peek(), LParen):
            stream.pop()
            if (body := Expression.try_lex(stream)) is None:
                raise LexError("Expected `Expression`.")
            stream.expect(RParen)
            return cls(body)
        return Literal.try_lex(stream) or Identifier.try_lex(stream)


DEFAULT_BINDING_POWER = (1.0, 1.1)
BINDING_POWER: dict[type[Token], tuple[int, int]] = {Asterisk: (5.0, 5.1)}


@lex_dataclass
class Infix(Lex):
    """Add: Atom '+' Atom;"""
    OPERATORS = (Plus, Asterisk, Comma, Equals)
    lhs: 'Atom'
    rhs: 'Atom'
    oper: 'Token'

    def _tree(self) -> tuple[str, list[Self]]:
        return f"Infix<{self.oper.value}>", [self.lhs, self.rhs]

    def __str__(self) -> str:
        return f"{self.lhs} {self.oper.value} {self.rhs}"

    def __repr__(self) -> str:
        return f"Infix<{self.lhs!r}{self.oper.value}{self.rhs!r}>"

    @classmethod
    def _try_lex(cls, stream: TokenStream, min_bp=0) -> Lex | None:
        lhs: Atom | Infix | None
        if (lhs := Atom.try_lex(stream)) is None:
            return

        while True:
            oper = stream.peek()
            if not any(isinstance(oper, o) for o in cls.OPERATORS):
                break
            l_bp, r_bp = BINDING_POWER.get(type(oper), DEFAULT_BINDING_POWER)
            if l_bp < min_bp:
                break
            stream.pop()
            if (rhs := cls.try_lex(stream, r_bp)) is None:
                break
            lhs = cls(lhs, oper, rhs)

        return lhs

    def check(self):
        self.lhs.check()
        self.rhs.check()


@lex_dataclass
class Expression(Lex):
    """Expression := Add | Identifier | Literal;"""
    value: Union[Infix, 'Atom']

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Expression<{self.value!r}>"

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Infix, Atom]

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
        stream.expect(Return, quiet=True)
        value = Expression.try_lex(stream)
        stream.expect(Semicolon)
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

    def _tree(self) -> tuple[str, list[Self]]:
        return 'ParamList' if self.params else 'ParamList (empty)', self.params

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(LParen, quiet=True)

        if isinstance(stream.peek(), RParen):
            stream.pop()
            return cls([])

        if (start := Identity.try_lex(stream)) is None:
            raise LexError("Expected Identity.")

        params = [start]
        while isinstance(stream.peek(), Comma):
            stream.pop()
            if (next := Identity.try_lex(stream)) is None:
                raise LexError("Expected Identity.")
            params.append(next)

        stream.expect(RParen)
        return cls(params)

    def check(self):
        for param in self.params:
            param.check()


@lex_dataclass
class ArrayDef(Lex):
    """ArrayDef: '[' [Number] ']';"""
    size: Number | None

    def __str__(self) -> str:
        if self.size is not None:
            return f"[{self.size.value}]"
        return "[]"

    def __repr__(self) -> str:
        return str(self)

    def _tree(self) -> tuple[str, list[Self]]:
        size = 'unsized' if self.size is None else self.size.value
        return f"ArrayDef<{size}>", []

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(LBracket, quiet=True)
        size = None
        if isinstance(stream.peek(), Number):
            size = stream.pop()
        stream.expect(RBracket)
        return cls(size)

    def check(self):
        if '.' in self.size.value:
            _LOG.error("Array sizes cannot be decimals.")


@lex_dataclass
class Type_(Lex):
    """Type_: Identifier [ ParamList ]"""

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

    def _tree(self) -> tuple[str, list[Self]]:
        return f"Type_<{self.ident}>", self.mods

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
    rhs: Union[Namespace, Type_]

    def __str__(self) -> str:
        if isinstance(self.rhs, Namespace):
            return str(self.lhs) + ": namespace"
        return f"{self.lhs}: {self.rhs}"

    def __repr__(self) -> str:
        return f"Identity<{self.lhs!r}, {self.rhs!r}>"

    def _tree(self) -> tuple[str, list[Self]]:
        return f"Identity<{self.lhs.value}>", [self.rhs]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (lhs := Identifier.try_lex(stream)) is None:
            return
        stream.expect(Colon)

        if isinstance(stream.peek(), Namespace):
            rhs = stream.pop()
        elif (rhs := Type_.try_lex(stream)) is None:
            raise LexError("Expected a `Type_` or 'namespace'.")

        return cls(lhs, rhs)

    def check(self) -> None:
        self.lhs.check()
        if not isinstance(self.rhs, Namespace):
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

    def _tree(self) -> tuple[str, list[Self]]:
        return f"Declaration<{self.identity}>", [] if self.initial is None else [self.initial]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (identity := Identity.try_lex(stream)) is None:
            return

        if not isinstance(stream.peek(), Equals):
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
        stream.expect(Semicolon)
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

    def _tree(self) -> tuple[str, list[Self]]:
        return "Scope", self.content

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        stream.expect(LBrace, quiet=True)
        ret = []
        while not isinstance(stream.peek(), RBrace) and ((res := ReturnStatement.try_lex(stream)) is not None or
                                                         (res := Statement.try_lex(stream)) is not None):
            ret.append(res)
        stream.expect(RBrace)
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

    def _tree(self) -> tuple[str, list[Self]]:
        return 'Document', self.statements

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        statements: list[Statement] = []
        while (res := Statement.try_lex(stream)):
            statements.append(res)
        return cls(statements)

    def check(self) -> None:
        for statement in self.statements:
            statement.check()
