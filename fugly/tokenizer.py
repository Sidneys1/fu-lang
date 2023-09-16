from abc import ABC, abstractmethod
from typing import Optional, TypeAlias, Iterator
from string import ascii_letters, digits
from inspect import isabstract

from . import ImmutableStream, Stream, ImmutableStrStream

ImmutableTokenStream: TypeAlias = ImmutableStream['Token', Stream['Token', 'TokenStream']]


class TokenStream(Stream['Token', 'TokenStream']):
    ...


class Token(ABC):
    __REGISTRY: dict[type['Token'], None] = {}

    value: str

    def __init__(self, value):
        self.value = value

    def __init_subclass__(cls) -> None:
        if not isabstract(cls) and ABC not in cls.__bases__:
            Token.__REGISTRY[cls] = None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}<{self.value}>"

    @staticmethod
    def get_next_token(istream: ImmutableStrStream) -> Optional['Token']:
        for token_type in Token.__REGISTRY:
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
    @abstractmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Optional['Token']:
        ...


class Char(Token, ABC):
    CHAR: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            if stream.peek() != cls.CHAR:
                return None
            val = stream.pop()
            stream.consume_whitespace()
            stream.commit()
            return cls(val)

    @classmethod
    def __str__(cls) -> str:
        return cls.__name__


class Colon(Char):
    CHAR = ':'


class LParen(Char):
    CHAR = '('


class RParen(Char):
    CHAR = ')'


class LBrace(Char):
    CHAR = '{'


class RBrace(Char):
    CHAR = '}'


class Equals(Char):
    CHAR = '='


class Plus(Char):
    CHAR = '+'


class Semicolon(Char):
    CHAR = ';'


class Comma(Char):
    CHAR = ','


class Keyword(Token, ABC):
    WORD: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            for char in cls.WORD:
                if stream.peek() != char:
                    return None
                stream.pop()
            stream.consume_whitespace()
            stream.commit()
            return cls(cls.WORD)

    @classmethod
    def __str__(cls) -> str:
        return cls.__name__


class Var(Keyword):
    WORD = 'var'


class Return(Keyword):
    WORD = 'return'


class CharClass(Token, ABC):
    START_CHARS: str = None
    CHARS: str

    @classmethod
    def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
        with istream.clone() as stream:
            if (peek := stream.peek()) not in (cls.START_CHARS or cls.CHARS):
                return None
            build = stream.pop()
            while not stream.eof and stream.peek() in cls.CHARS:
                build += stream.pop()
            stream.consume_whitespace()
            stream.commit()
            return cls(build)


class Word(CharClass):
    START_CHARS = ascii_letters + '_'
    CHARS = ascii_letters + digits + '_'


class Number(CharClass):
    CHARS = digits
