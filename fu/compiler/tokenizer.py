from typing import TypeAlias, Iterator
from string import ascii_letters, digits
from enum import Enum
from dataclasses import dataclass, field

from . import ImmutableStream, Stream, SourceLocation

ImmutableTokenStream: TypeAlias = ImmutableStream['Token', Stream['Token', 'TokenStream']]


class TokenStream(Stream['Token', 'TokenStream']):
    ...


WORD_START = ascii_letters + '_'
NUMBER_START = digits
NUMBER_END = 'fF'
WHITESPACE = ' \t\r\n'


class TokenType(Enum):
    String = 'string'
    Colon = ':'
    LParen = '('
    RParen = ')'
    LBrace = '{'
    RBrace = '}'
    LBracket = '['
    RBracket = ']'
    Equals = '='
    Operator = '+-*/!'
    Semicolon = ';'
    Comma = ','
    Dot = '.'
    LessThan = '<'
    GreaterThan = '>'
    ReturnKeyword = 'return'
    NamespaceKeyword = 'namespace'
    Word = WORD_START + digits
    Number = NUMBER_START + '._'
    Comment = 'comment'
    BlockComment = 'block_comment'
    BlankLine = 'blank_line'
    SpecialOperator = 'op'


class SpecialOperatorType(Enum):
    Constructor = 'op='
    Call = 'op()'


SPECIAL_OPERATORS = {x.value[2]: x for x in SpecialOperatorType}
"""
Special operators follow the pattern `op???`. E.g., `op=`, `op()`.

This table holds a mapping of the first character afer `op` to specific type of special operator it should be.
"""

TOKEN_REVERSE_MAP = {e.value: e for e in TokenType}


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Token:
    """Represents a parsed token, including its value, type, and location."""
    value: str
    type: TokenType
    location: SourceLocation
    surround: list['Token'] = field(default_factory=list, kw_only=True)
    special_op_type: SpecialOperatorType | None = field(kw_only=True, default=True)

    def __repr__(self) -> str:
        return f"{self.type.name}<{self.value!r}@{self.location}>"

    def __eq__(self, value: object) -> bool:
        if isinstance(value, TokenType):
            return self.type == value
        if isinstance(value, Token):
            return self.value == value.value and self.type == value.type and self.location == value.location
        return super().__eq__(value)

    @staticmethod
    def token_generator(stream: Stream[str, 'Stream']) -> Iterator['Token']:
        """Generate tokens from a stream of characters."""

        def _pos(start_pos, end_pos):
            return SourceLocation(*zip(start_pos, end_pos))

        if stream.eof:
            return

        def y(value: str, type: TokenType, location: SourceLocation, special_operator_type=None):
            nonlocal surround
            s = surround
            surround = list()
            return Token(value, type, location, surround=s, special_op_type=special_operator_type)

        start_pos = stream.position
        char = stream.pop()
        surround = []
        in_between = start_pos
        blank_lines = 0
        while char is not None:
            # print(f'read {char!r}')
            if char in WHITESPACE:
                if char == '\n':
                    if in_between is not None:
                        blank_lines += 1
                    else:
                        in_between = start_pos
                start_pos = stream.position
                char = stream.pop()
                continue
            elif in_between is not None:
                if blank_lines:
                    surround.append(Token('\n' * (blank_lines - 1), TokenType.BlankLine, _pos(in_between, start_pos)))
                in_between = None
                blank_lines = 0

            if char == '/' and not stream.eof:
                char = stream.pop()
                if char == '/':
                    buffer = '//'
                    char = stream.pop()
                    while not stream.eof and char != '\n':
                        buffer += char
                        end_pos = stream.position
                        char = stream.pop()
                    surround.append(Token(buffer, TokenType.Comment, _pos(start_pos, end_pos)))
                    start_pos = end_pos
                    continue
                if char == '*':
                    buffer = '/*'
                    char = stream.pop()
                    while True:
                        if stream.eof:
                            raise EOFError()
                        buffer += char
                        end_pos = stream.position
                        char = stream.pop()
                        if buffer[-1] == '*' and char == '/':
                            break
                    surround.append(Token(buffer, TokenType.Comment, _pos(start_pos, end_pos)))
                    start_pos = end_pos
                    continue
            # elif char == '\\' and not stream.eof:
            #     # Skip next character entirely. If it's a carriage return, also ignore newline (Windows encoding)
            #     if stream.pop() == '\r' and stream.peek() == '\n':
            #         stream.pop()
            elif char == '"':
                # Some string, let's build up a buffer.
                buffer = ''
                char = stream.pop()
                while not stream.eof and char != '"':
                    buffer += char
                    char = stream.pop()
                end_pos = stream.position
                npos = stream.position
                char = stream.pop()
                yield y(buffer, TokenType.String, _pos(start_pos, end_pos))
                start_pos = npos
                continue
            elif (tt := TOKEN_REVERSE_MAP.get(char, None)) is not None:
                yield y(char, tt, _pos(start_pos, start_pos))
            elif char in TokenType.Operator.value:
                yield y(char, TokenType.Operator, _pos(start_pos, start_pos))
            elif char in WORD_START:
                # Some alphanumeric, let's build up a buffer.
                buffer = ''
                last_pos = start_pos
                npos = start_pos
                while char is not None and char in TokenType.Word.value:
                    buffer += char
                    end_pos = last_pos
                    last_pos = stream.position
                    npos = stream.position
                    char = stream.pop()
                if buffer == 'op' and char in SPECIAL_OPERATORS:
                    t = SPECIAL_OPERATORS[char]
                    while char is not None and len(buffer) < len(t.value) and char == t.value[len(buffer)]:
                        buffer += char
                        end_pos = last_pos
                        last_pos = stream.position
                        npos = stream.position
                        char = stream.pop()
                    if buffer != t.value:
                        raise ValueError(f"I don't undertsand the token {buffer!r} (expected {t.value}).")
                    yield y(buffer, TokenType.SpecialOperator, _pos(start_pos, end_pos), special_operator_type=t)
                    continue
                yield y(buffer, TOKEN_REVERSE_MAP.get(buffer, TokenType.Word), _pos(start_pos, end_pos))
                start_pos = npos
                continue
            elif char in NUMBER_START:
                # Some numeric, let's build up a buffer.
                buffer = ''
                last_pos = start_pos
                while char is not None and char in TokenType.Number.value:
                    buffer += char
                    last_pos = stream.position
                    end_pos = start_pos
                    char = stream.pop()
                if char in NUMBER_END:
                    buffer += char
                    end_pos = last_pos
                    char = stream.pop()
                yield y(buffer, TokenType.Number, _pos(start_pos, end_pos))
                start_pos = end_pos
                continue
            else:
                raise ValueError(f"I don't under stand the character {char!r} at {start_pos}")

            start_pos = stream.position
            char = stream.pop()


# class String(Token, type=TokenType.String):
#     DISALLOWED = '\r\n'

#     @classmethod
#     def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
#         with istream.clone() as stream:
#             if stream.peek() not in ('"', "'"):
#                 return None
#             start_pos = stream.position
#             start = stream.pop()
#             builder = start
#             while True:
#                 if stream.eof:
#                     raise EOFError()
#                 c = stream.pop()
#                 if c in cls.DISALLOWED:
#                     raise RuntimeError()
#                 builder += c
#                 if c == '\\':
#                     if stream.eof:
#                         raise EOFError()
#                     if stream.peek() in cls.DISALLOWED:
#                         raise RuntimeError()
#                     builder += stream.pop()
#                     continue
#                 if c == start:
#                     break
#             end_pos = stream.position
#             stream.consume_whitespace()
#             stream.commit()
#             return Token(
#                 builder, Token._REGISTRY[cls],
#                 TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))

# class Char(Token, ABC):
#     CHAR: str

#     @classmethod
#     def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
#         with istream.clone() as stream:
#             if stream.peek() != cls.CHAR:
#                 return None
#             start_pos = stream.position
#             val = stream.pop()
#             stream.consume_whitespace()
#             stream.commit()
#             return Token(
#                 val, Token._REGISTRY[cls],
#                 TokenPosition((start_pos[0], start_pos[0]), (start_pos[1], start_pos[1]), (start_pos[2], start_pos[2])))

#     @classmethod
#     def __str__(cls) -> str:
#         return cls.__name__

# class Colon(Char, type=TokenType.Colon):
#     CHAR = ':'

# class LParen(Char, type=TokenType.LParen):
#     CHAR = '('

# class RParen(Char, type=TokenType.RParen):
#     CHAR = ')'

# class LBrace(Char, type=TokenType.LBrace):
#     CHAR = '{'

# class RBrace(Char, type=TokenType.RBrace):
#     CHAR = '}'

# class LBracket(Char, type=TokenType.LBracket):
#     CHAR = '['

# class RBracket(Char, type=TokenType.RBracket):
#     CHAR = ']'

# class Equals(Char, type=TokenType.Equals):
#     CHAR = '='

# class Semicolon(Char, type=TokenType.Semicolon):
#     CHAR = ';'

# class Comma(Char, type=TokenType.Comma):
#     CHAR = ','

# class Keyword(Token, ABC):
#     WORD: str

#     @classmethod
#     def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
#         with istream.clone() as stream:
#             start_pos = stream.position
#             for char in cls.WORD:
#                 if stream.peek() != char:
#                     return None
#                 stream.pop()
#             end_pos = stream.position
#             stream.consume_whitespace()
#             stream.commit()
#             return Token(
#                 cls.WORD, Token._REGISTRY[cls],
#                 TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))

#     @classmethod
#     def __str__(cls) -> str:
#         return cls.__name__

# class Return(Keyword, type=TokenType.ReturnKeyword):
#     WORD = 'return'

# class Namespace(Keyword, type=TokenType.NamespaceKeyword):
#     WORD = 'namespace'

# class CharClass(Token, ABC):
#     START_CHARS: str = None
#     CHARS: str

#     @classmethod
#     def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
#         with istream.clone() as stream:
#             start_pos = stream.position
#             if (peek := stream.peek()) not in (cls.START_CHARS or cls.CHARS):
#                 return None
#             build = stream.pop()
#             while not stream.eof and stream.peek() in cls.CHARS:
#                 build += stream.pop()
#             end_pos = stream.position
#             stream.consume_whitespace()
#             stream.commit()
#             return Token(
#                 build, Token._REGISTRY[cls],
#                 TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))

# class Word(CharClass, type=TokenType.Word):
#     START_CHARS = ascii_letters + '_'
#     CHARS = ascii_letters + digits + '_'

# class Number(CharClass, type=TokenType.Number):
#     START_CHARS = digits
#     CHARS = digits + '._'

# class SingleCharClass(Token, ABC):
#     CHARS: str

#     @classmethod
#     def try_consume(cls, istream: ImmutableStrStream) -> Token | None:
#         with istream.clone() as stream:
#             start_pos = stream.position
#             if (peek := stream.peek()) not in cls.CHARS:
#                 return None
#             char = stream.pop()
#             end_pos = stream.position
#             stream.consume_whitespace()
#             stream.commit()
#             return Token(
#                 char, Token._REGISTRY[cls],
#                 TokenPosition((start_pos[0], end_pos[0]), (start_pos[1], end_pos[1]), (start_pos[2], end_pos[2])))

# class Operator(SingleCharClass, type=TokenType.Operator):
#     CHARS = '+-*/!'
