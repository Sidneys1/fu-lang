from abc import ABC, abstractmethod
from typing import Optional, TypeAlias, Iterator
from string import ascii_letters, digits
from inspect import isabstract
from enum import Enum, auto
from dataclasses import dataclass

from . import ImmutableStream, Stream, ImmutableStrStream, TokenPosition

ImmutableTokenStream: TypeAlias = ImmutableStream['Token', Stream['Token', 'TokenStream']]


class TokenStream(Stream['Token', 'TokenStream']):
    ...


class TokenType(Enum):
    String = auto()
    Colon = auto()
    LParen = auto()
    RParen = auto()
    LBrace = auto()
    RBrace = auto()
    LBracket = auto()
    RBracket = auto()
    Equals = auto()
    Operator = auto()
    Semicolon = auto()
    Comma = auto()
    ReturnKeyword = auto()
    NamespaceKeyword = auto()
    Word = auto()
    Number = auto()


# @dataclass(repr=False, frozen=True, slots=True)
class Token:
    _REGISTRY: dict[type['Token'], TokenType] = {}

    value: str
    type_: TokenType
    location: TokenPosition

    def __init__(self, value, type, location) -> None:
        self.value = value
        self.type_ = type
        self.location = location

    def __init_subclass__(cls, type: TokenType = None) -> None:
        if not isabstract(cls) and ABC not in cls.__bases__:
            if type is None: raise RuntimeError(f"{cls.__name__} does not have an associated TokenType")
            Token._REGISTRY[cls] = type

    def __repr__(self) -> str:
        return f"{self.type_.name}<{self.value}>"

    @staticmethod
    def get_next_token(istream: ImmutableStrStream) -> Optional['Token']:
        for token_type in Token._REGISTRY:
            if (ret := token_type.try_consume(istream)) is not None:
                return ret
        return None

    @staticmethod
    def token_generator(istream: ImmutableStrStream) -> Iterator['Token']:
        while not istream.eof:
            ret = Token.get_next_token(istream)
            if ret is None: return
            yield ret

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Optional['Token']:
        ...


class String(Token, type=TokenType.String):
    DISALLOWED = '\r\n'

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            if stream.peek() not in ('"', "'"):
                return None
            start_pos = stream.position
            start = stream.pop()
            builder = start
            while True:
                if stream.eof:
                    raise EOFError()
                c = stream.pop()
                if c in cls.DISALLOWED:
                    raise RuntimeError()
                builder += c
                if c == '\\':
                    if stream.eof:
                        raise EOFError()
                    if stream.peek() in cls.DISALLOWED:
                        raise RuntimeError()
                    builder += stream.pop()
                    continue
                if c == start:
                    break
            end_pos = stream.position
            stream.consume_whitespace()
            stream.commit()
            return Token(
                builder, Token._REGISTRY[cls],
                TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))


class Char(Token, ABC):
    CHAR: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            if stream.peek() != cls.CHAR:
                return None
            start_pos = stream.position
            val = stream.pop()
            stream.consume_whitespace()
            stream.commit()
            return Token(
                val, Token._REGISTRY[cls],
                TokenPosition((start_pos[0], start_pos[0]), (start_pos[1], start_pos[1]), (start_pos[2], start_pos[2])))

    @classmethod
    def __str__(cls) -> str:
        return cls.__name__


class Colon(Char, type=TokenType.Colon):
    CHAR = ':'


class LParen(Char, type=TokenType.LParen):
    CHAR = '('


class RParen(Char, type=TokenType.RParen):
    CHAR = ')'


class LBrace(Char, type=TokenType.LBrace):
    CHAR = '{'


class RBrace(Char, type=TokenType.RBrace):
    CHAR = '}'


class LBracket(Char, type=TokenType.LBracket):
    CHAR = '['


class RBracket(Char, type=TokenType.RBracket):
    CHAR = ']'


class Equals(Char, type=TokenType.Equals):
    CHAR = '='


class Semicolon(Char, type=TokenType.Semicolon):
    CHAR = ';'


class Comma(Char, type=TokenType.Comma):
    CHAR = ','


class Keyword(Token, ABC):
    WORD: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            start_pos = stream.position
            for char in cls.WORD:
                if stream.peek() != char:
                    return None
                stream.pop()
            end_pos = stream.position
            stream.consume_whitespace()
            stream.commit()
            return Token(
                cls.WORD, Token._REGISTRY[cls],
                TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))

    @classmethod
    def __str__(cls) -> str:
        return cls.__name__


class Return(Keyword, type=TokenType.ReturnKeyword):
    WORD = 'return'


class Namespace(Keyword, type=TokenType.NamespaceKeyword):
    WORD = 'namespace'


class CharClass(Token, ABC):
    START_CHARS: str = None
    CHARS: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            start_pos = stream.position
            if (peek := stream.peek()) not in (cls.START_CHARS or cls.CHARS):
                return None
            build = stream.pop()
            while not stream.eof and stream.peek() in cls.CHARS:
                build += stream.pop()
            end_pos = stream.position
            stream.consume_whitespace()
            stream.commit()
            return Token(
                build, Token._REGISTRY[cls],
                TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))


class Word(CharClass, type=TokenType.Word):
    START_CHARS = ascii_letters + '_'
    CHARS = ascii_letters + digits + '_'


class Number(CharClass, type=TokenType.Number):
    START_CHARS = digits
    CHARS = digits + '._'


class SingleCharClass(Token, ABC):
    CHARS: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            start_pos = stream.position
            if (peek := stream.peek()) not in cls.CHARS:
                return None
            char = stream.pop()
            end_pos = stream.position
            stream.consume_whitespace()
            stream.commit()
            return Token(
                char, Token._REGISTRY[cls],
                TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))


class Operator(SingleCharClass, type=TokenType.Operator):
    CHARS = '+-*/!'
