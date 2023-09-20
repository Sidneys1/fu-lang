from abc import ABC
from typing import Iterable, Optional, Union, Self
from logging import getLogger
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass as _dataclass

from fugly.tokenizer import ImmutableTokenStream, Optional

from .tokenizer import *

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


class Lex(ABC):

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Optional['Lex']:
        raise NotImplementedError()

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
    """
    Identifier: Word
    """
    value: str

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return self.value

    def _tree(self) -> tuple[str, list[Self]]:
        return f'Identifier<{self.value}>', []

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Identifier`", "| " * istream.depth)
        with istream.clone() as stream:
            value = stream.pop()
            if not isinstance(value, Word):
                _LOG.warn(f"%sExpected Word, got {value}", 'x ' * istream.depth)
                return
            stream.commit()
            ret = cls(value.value)
            _LOG.debug("%sGot %r!", '| ' * stream.depth, ret)
            return ret


class Literal(Lex):
    """
    Literal: String | Number;
    """
    value: str

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return self.value

    def _tree(self) -> tuple[str, list[Self]]:
        return self.value, []

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Literal`", '| ' * istream.depth)
        with istream.clone() as stream:
            value = stream.pop()
            if not (isinstance(value, String) or isinstance(value, Number)):
                return
            stream.commit()
            return cls(value.value)


class Atom(Lex):
    """
    Atom: Literal | Identifier | '(' Expression ')'
    """
    value: Union[Literal, Identifier, 'Expression']

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return f"({self.value})" if isinstance(self.value, Expression) else self.value.value

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Atom`", '| ' * istream.depth)
        with istream.clone() as stream:
            boundary = stream.peek()

            if isinstance(boundary, LParen):
                boundary.pop()
                if (body := Expression.try_lex(stream)) is None:
                    return
                if not isinstance(stream.pop(), RParen):
                    return
                stream.commit()
                return cls(body)

            value = Literal.try_lex(stream) or Identifier.try_lex(stream)
            if value is None:
                return

            stream.commit()
            return value


DEFAULT_BINDING_POWER = (1.0, 1.1)
BINDING_POWER: dict[type[Token], tuple[int, int]] = {Asterisk: (5.0, 5.1)}


class Infix(Lex):
    """
    Add: Atom '+' Atom;
    """
    OPERATORS = (Plus, Asterisk, Comma)
    lhs: 'Atom'
    rhs: 'Atom'
    oper: 'Token'

    def __init__(self, lhs, oper, rhs):
        self.lhs = lhs
        self.oper = oper
        self.rhs = rhs

    def _tree(self) -> tuple[str, list[Self]]:
        return f"Infix<{self.oper.value}>", [self.lhs, self.rhs]

    def __str__(self) -> str:
        return f"{self.lhs} {self.oper.value} {self.rhs}"

    def __repr__(self) -> str:
        return f"Infix<{self.lhs!r}{self.oper.value}{self.rhs!r}>"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream, min_bp=0) -> Lex | None:
        _LOG.debug("%sTrying to lex `Infix`", '| ' * istream.depth)
        with istream.clone() as stream:
            lhs: Atom | Infix | None
            if (lhs := Atom.try_lex(stream)) is None:
                _LOG.warn("%sExpected Atom", '| ' * istream.depth)
                return
            if stream.eof:
                _LOG.debug("%sGot EOF", 'x ' * istream.depth)
                return

            while True:
                oper = stream.peek()
                if not any(isinstance(oper, o) for o in cls.OPERATORS):
                    _LOG.warn("%sExpected ('%s'), got '%s'", '| ' * istream.depth,
                              "'|'".join(o.CHAR for o in cls.OPERATORS), oper.value)
                    break
                l_bp, r_bp = BINDING_POWER.get(type(oper), DEFAULT_BINDING_POWER)
                if l_bp < min_bp:
                    break
                stream.pop()
                if (rhs := cls.try_lex(stream, r_bp)) is None:
                    _LOG.warn("%sExpected Atom", '| ' * istream.depth)
                    break
                lhs = cls(lhs, oper, rhs)

            stream.commit()
            return lhs


class Expression(Lex):
    """
    Expression := Add | Identifier | Literal;
    """
    value: Union[Infix, 'Atom', 'Assignment']

    def __init__(self, value) -> None:
        self.value = value

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Expression<{self.value!r}>"

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Assignment, Infix, Atom]

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Expression`", '| ' * istream.depth)
        with istream.clone() as stream:
            for t in cls.allowed:
                ret = t.try_lex(stream)
                if ret is not None:
                    _LOG.debug("%sWas an Expression!", '| ' * istream.depth)
                    stream.commit()
                    return cls(ret)


class ReturnStatement(Lex):
    """
    ReturnStatement: 'return' Expression;
    """
    value: 'Expression'

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return f"{_tab()}return {self.value};\n"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `ReturnStatement`", '| ' * istream.depth)
        with istream.clone() as stream:
            if not isinstance(stream.pop(), Return):
                return
            value = Expression.try_lex(stream)
            if value is None and not isinstance(value := stream.pop(), Word):
                _LOG.warn("Expected Expression or Identifier, got %s", value.value)
                return None
            if not isinstance((x := stream.pop()), Semicolon):
                _LOG.warn("Expected ;, got %r", x.value)
                return
            stream.commit()
            return cls(value)


class Assignment(Lex):
    """
    Assignment := Identifier '=' Expression
    """
    lhs: Identifier
    rhs: Expression

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    def __str__(self) -> str:
        return f"{self.lhs} = {self.rhs}"

    def __repr__(self) -> str:
        return f"Assignment<{self.lhs!r}={self.rhs!r}>"

    def _tree(self) -> tuple[str, list[Self]]:
        return 'Assignment', [self.lhs, self.rhs]

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Assignment`", '| ' * istream.depth)
        with istream.clone() as stream:
            lhs: Identifier | None = None
            if stream.eof:
                return
            lhs = Identifier.try_lex(stream)
            if lhs is None:
                return

            if lhs is None:
                _LOG.warn("%sExpected Identifier", '| ' * istream.depth)
                return
            if not isinstance(stream.pop(), Equals):
                _LOG.warn("%sExpected =", '| ' * istream.depth)
                return
            rhs = Expression.try_lex(stream)
            if rhs is None:
                return

            stream.commit()
            return cls(lhs, rhs)


@lex_dataclass
class ParamList(Lex):
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
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug('%sTrying to lex `ParamList`', '| ' * istream.depth)
        with istream.clone() as stream:
            if not isinstance(stream.pop(), LParen):
                return
            if isinstance(stream.peek(), RParen):
                stream.pop()
                stream.commit()
                return cls([])
            if (start := Identity.try_lex(stream)) is None:
                _LOG.warn("%sExpected Identity", 'x ' * istream.depth)
                return
            params = [start]
            while isinstance(stream.peek(), Comma):
                stream.pop()
                if (next := Identity.try_lex(stream)) is None:
                    _LOG.warn("Was not a Identity!")
                    return
                params.append(next)
            if not isinstance((x := stream.pop()), RParen):
                _LOG.warn("%sExpected ')', got %r", 'x ' * istream.depth, x.value)
                return
            stream.commit()
            ret = cls(params)
            _LOG.debug("%sGot %r", '| ' * istream.depth, ret)
            return cls(params)


@lex_dataclass
class ArrayDef(Lex):
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
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `ArrayDef`", '| ' * istream.depth)
        with istream.clone() as stream:
            if not isinstance(stream.pop(), LBracket):
                return
            size = None
            if isinstance(stream.peek(), Number):
                size = stream.pop()
            if not isinstance((x := stream.pop()), RBracket):
                _LOG.warn("%sExpected ']', got %r", 'x ' * istream.depth, x.value)
                return
            stream.commit()
            return cls(size)


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
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Type_`", '| ' * istream.depth)
        with istream.clone() as stream:
            if (ident := Identifier.try_lex(stream)) is None:
                return
            mods = []
            while (mod := (ParamList.try_lex(stream) or ArrayDef.try_lex(stream))) is not None:
                mods.append(mod)
            stream.commit()
            return cls(ident, mods)


@lex_dataclass
class Identity(Lex):
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
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to parse Identity", '| ' * istream.depth)
        with istream.clone() as stream:
            if (lhs := Identifier.try_lex(stream)) is None:
                return
            if not isinstance((x := stream.pop()), Colon):
                _LOG.warn("%sExpected ':', got %s", 'x ' * istream.depth, x.value)
                return
            if stream.eof:
                _LOG.warn("%sExpected 'namespace'|Type_, got EoF", "x " * istream.depth)
                return
            if isinstance(stream.peek(), Namespace):
                rhs = stream.pop()
            elif (rhs := Type_.try_lex(stream)) is None:
                _LOG.debug("%sExpected Type_", 'x ' * istream.depth)
                return

            stream.commit()
            return cls(lhs, rhs)


class Declaration(Lex):
    """
    Declaration := Identifier ':' Identifier [ '=' Expression ]
    """
    identity: Identity
    initial: Union['Scope', 'Expression', None] = None

    def __init__(self, type_sig, initial=None):
        self.identity = type_sig
        self.initial = initial

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
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Declaration`", '| ' * istream.depth)
        with istream.clone() as stream:
            if (identity := Identity.try_lex(stream)) is None:
                _LOG.warn("%sExpected Identity", '| ' * istream.depth)
                return

            if not isinstance(stream.peek(), Equals):
                stream.commit()
                _LOG.debug("%sWas a Declaration (without initial value)!", "y " * istream.depth)
                return cls(identity)
            stream.pop()

            val = Scope.try_lex(stream) or Expression.try_lex(stream)
            if val is None:
                _LOG.warn("Expected expression")
                return

            stream.commit()
            _LOG.debug("%sWas a Declaration (with value)!", "y " * istream.depth)
            return cls(identity, val)


class Statement(Lex):
    """
    Statement: Declaration | Expression;
    """
    value: Union['Expression', 'Declaration']

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Declaration, Expression]

    def __init__(self, content):
        self.value = content

    def __str__(self) -> str:
        return f'{_tab()}{self.value};\n'

    def __repr__(self) -> str:
        return f"Statement<{self.value!r}>"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Statement`", '| ' * istream.depth)
        with istream.clone() as stream:
            res = None
            for t in cls.allowed:
                # _LOG.debug(f"%sTrying {t.__name__}", '| ' * istream.depth)
                if (res := t.try_lex(stream)) is not None:
                    break

            if not isinstance((t := stream.pop()), Semicolon):
                _LOG.warn("%sExpected ';', got %r", '| ' * istream.depth, t.value)
                return

            stream.commit()
            _LOG.debug("%sWas a Statement!", 'y ' * istream.depth)
            return cls(res)


@lex_dataclass
class Scope(Lex):
    content: list['ReturnStatement', 'Statement']

    def __str__(self) -> str:
        with _indent():
            inner = ''.join(str(x) for x in self.content)
        if inner:
            inner = '\n' + inner
        return '{' + inner + _tab() + '}'

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.content)
        return f"Scope<{inner}>"

    def _tree(self) -> tuple[str, list[Self]]:
        return "Scope", self.content

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Scope`", '| ' * istream.depth)
        with istream.clone() as stream:
            if not isinstance((tok := stream.pop()), LBrace):
                _LOG.warn('Expected {, got %r', tok.value)
                return
            ret = []
            while not stream.eof and not isinstance(stream.peek(), RBrace) and (
                (res := ReturnStatement.try_lex(stream)) is not None or (res := Statement.try_lex(stream)) is not None):
                ret.append(res)
            if stream.eof:
                _LOG.warn("Expected }, got EOF")
                return
            if not isinstance((tok := stream.pop()), RBrace):
                _LOG.warn('Expected }, got %r', tok.value)
                return
            stream.commit()
            _LOG.debug("%sWas a Scope!", 'y ' * istream.depth)
            return cls(ret)


@lex_dataclass
class Document(Lex):
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
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("%sTrying to lex `Document`", "| " * istream.depth)
        with istream.clone() as stream:
            statements: list[Statement] = []
            while not stream.eof and (res := Statement.try_lex(stream)) is not None:
                statements.append(res)
            if not stream.eof:
                _LOG.warn("%sLex of Document did not consume entire file!", "| " * stream.depth)
                return None
            stream.commit()
            return cls(statements)
