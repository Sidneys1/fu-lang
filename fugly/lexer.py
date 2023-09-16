from abc import ABC, abstractmethod
from typing import Iterator, Iterable, Optional, Union
from logging import getLogger

from fugly.tokenizer import ImmutableTokenStream, Optional

from .tokenizer import *

_LOG = getLogger(__name__)


class Lex(ABC):

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Optional['Lex']:
        raise NotImplementedError()
        # print('lex')
        # curr: Lex | None = None
        # for t in cls.valid_children():
        #     for l in t.try_lex(istream, seed=curr):
        #         curr = l
        # if curr is not None:
        #     yield curr


"""
var x: i32 = y + 1;
    N   T    L   R
^-declar-^  ^expr^
^---ASSIGNMENT---^
^------LINE-------^
"""


class Scope(Lex):
    ...


class Body(Lex):
    content: list['ReturnStatement', 'Statement']

    def __init__(self, content):
        self.content = content

    def __str__(self) -> str:
        return '{\n\t' + '\t'.join(str(x) for x in self.content) + '}\n'

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Body`")
        with istream.clone() as stream:
            if not isinstance((tok := stream.pop()), LBrace):
                _LOG.warn('Expected {, got %r', tok.value)
                return
            ret = []
            while not stream.eof and ((res := ReturnStatement.try_lex(stream)) is not None or
                                      (res := Statement.try_lex(stream)) is not None):
                ret.append(res)
            if stream.eof:
                _LOG.warn("Expected }, got EOF")
                return
            if not isinstance((tok := stream.pop()), RBrace):
                _LOG.warn('Expected }, got %r', tok.value)
                return
            stream.commit()
            _LOG.debug("Was a Body!")
            return cls(ret)


class ReturnStatement(Lex):
    value: Union['Expression', 'Word']

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return f"return {self.value};\n"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `ReturnStatement`")
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


class Statement(Lex):
    content: list[Union['Expression', 'Declaration']]

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Declaration, Expression]

    def __init__(self, content):
        self.content = content

    def __str__(self) -> str:
        return ', '.join(str(c) for c in self.content) + ';\n'

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Statement`")
        with istream.clone() as stream:
            res = []
            while not stream.eof:
                for t in cls.allowed:
                    _LOG.debug(f"Trying {t.__name__}")
                    if (t := t.try_lex(stream)) is not None:
                        res.append(t)
                        break
                if not isinstance((t := stream.peek()), Comma):
                    _LOG.warn("Expected ',', got %r", t.value)
                    break
                stream.pop()

            if not isinstance((t := stream.pop()), Semicolon):
                _LOG.warn("Expected ';', got %r", t.value)
                return

            stream.commit()
            _LOG.debug("Was a Statement!")
            return cls(res)


class Declaration(Lex):
    name: Word
    type_: Word
    initial: 'Expression'

    def __init__(self, name, type_, initial=None):
        self.name = name
        self.type_ = type_
        self.initial = initial

    def __str__(self) -> str:
        if self.initial is not None:
            return f"var {self.name.value}: {self.type_.value} = {self.initial}"
        return f"var {self.name.value}: {self.type_.value}"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Declaration`")
        with istream.clone() as stream:
            if not isinstance(stream.pop(), Var):
                _LOG.warn("Expected 'var'")
                return
            name = stream.pop()
            if not isinstance(name, Word):
                _LOG.warn("Expected Identifier")
                return
            if not isinstance(stream.pop(), Colon):
                _LOG.warn("Expected colon")
                return
            type_ = stream.pop()
            if not isinstance(type_, Word):
                _LOG.warn("Expected Identifier")
                return

            if not isinstance(stream.peek(), Equals):
                stream.commit()
                _LOG.debug("Was a Declaration (without initial value)!")
                return cls(name, type_)

            stream.pop()
            val = Expression.try_lex(stream)
            if val is None:
                _LOG.warn("Expected expression")
                return

            stream.commit()
            _LOG.debug("Was a Declaration!")
            return cls(name, type_, val)


class Add(Lex):
    lhs: Word | Number
    rhs: Word | Number

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    def __str__(self) -> str:
        return f"{self.lhs.value} + {self.rhs.value}"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Add`")
        with istream.clone() as stream:
            lhs = stream.pop()
            if not (isinstance(lhs, Word) or isinstance(lhs, Number)):
                _LOG.warn("Expected Identifier or Number")
                return
            if not isinstance(stream.pop(), Plus):
                _LOG.warn("Expected +")
                return
            rhs = stream.pop()
            if not (isinstance(rhs, Word) or isinstance(rhs, Number)):
                _LOG.warn("Expected Identifier or Number")
                return

            stream.commit()
            _LOG.debug("Was an Add!")
            return cls(lhs, rhs)


class Identifier(Lex):
    value: str

    def __init__(self, value):
        self.value = value

    def __str__(self) -> str:
        return self.value

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Identifier`")
        with istream.clone() as stream:
            value = stream.pop()
            if not isinstance(value, Word):
                return
            stream.commit()
            return cls(value.value)


class Expression(Lex):

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Add, Identifier]

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Expression`")
        for t in cls.allowed:
            ret = t.try_lex(istream)
            if ret is not None:
                _LOG.debug("Was an Expression!")
                return ret


class Assignment(Lex):
    lhs: Identifier
    rhs: Expression

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    def __str__(self) -> str:
        return f"{self.lhs} = {self.rhs}"

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Lex | None:
        _LOG.debug("Trying to lex `Assignment`")
        with istream.clone() as stream:
            lhs: Identifier | None = None
            if stream.eof:
                return
            lhs = Identifier.try_lex(stream)
            if lhs is None:
                return

            if lhs is None:
                _LOG.warn("Expected Identifier or Declaration")
                return
            if not isinstance(stream.pop(), Equals):
                _LOG.warn("Expected =")
                return
            rhs = Expression.try_lex(stream)
            if rhs is None:
                return

            stream.commit()
            return cls(lhs, rhs)
