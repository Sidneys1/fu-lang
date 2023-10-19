from typing import Iterator, Iterable
from string import ascii_letters, digits
from enum import Enum, auto
from dataclasses import dataclass, field
from itertools import product

from . import StrStream, SourceLocation

_SIGNEDNESS = ('iu')
_SIZE = ('8', '16', '32', '64')
INT_ENDS = ('i', 'u', *(a + b for a, b in product(_SIGNEDNESS, _SIZE)))
FLOAT_ENDS = ('f16', 'f', 'f32', 'd', 'f64')

WORD_START = ascii_letters + '_'
NUMBER_START = digits
NUMBER_END = (*INT_ENDS, *FLOAT_ENDS)
WHITESPACE = ' \t\r\n'


class TokenType(Enum):
    EOF = auto()
    String = auto()
    Comment = auto()
    BlockComment = auto()
    BlankLine = auto()
    SpecialOperator = auto()

    # Symbols
    Colon = ':'
    LParen = '('
    RParen = ')'
    LBrace = '{'
    RBrace = '}'
    LBracket = '['
    RBracket = ']'
    Equals = '='
    Semicolon = ';'
    Comma = ','
    Dot = '.'
    LessThan = '<'
    GreaterThan = '>'

    # Keywords
    ReturnKeyword = 'return'
    NamespaceKeyword = 'namespace'

    # Char classes
    Operator = '+-*/!'
    Word = WORD_START + digits
    Number = NUMBER_START + '._'


NON_CODE_TOKEN_TYPES = (TokenType.Comment, TokenType.BlockComment, TokenType.BlankLine)


class SpecialOperatorType(Enum):
    Constructor = 'op='
    Call = 'op()'
    Index = 'op[]'


SPECIAL_OPERATORS = {x.value[2]: x for x in SpecialOperatorType}
"""
Special operators follow the pattern `op???`. E.g., `op=`, `op()`.

This table holds a mapping of the first character afer `op` to specific type of special operator it should be.
"""

_REVERSE_MAP_EXCLUDE = (TokenType.Word, TokenType.Number, TokenType.Operator)
TOKEN_REVERSE_MAP = {e.value: e for e in TokenType if isinstance(e.value, str) and e not in _REVERSE_MAP_EXCLUDE}


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Token:
    """Represents a parsed token, including its value, type, and location."""
    value: str
    type: TokenType
    location: SourceLocation
    # surround: list['Token'] = field(default_factory=list, kw_only=True)
    special_op_type: SpecialOperatorType | None = field(kw_only=True, default=None)

    def __repr__(self) -> str:
        return f"{self.type.name}<{self.value!r}@{self.location}>"

    def __eq__(self, value: object) -> bool:
        if isinstance(value, TokenType):
            return self.type == value
        if isinstance(value, Token):
            return self.value == value.value and self.type == value.type and self.location == value.location
        return False
        # return super().__eq__(value)

    @staticmethod
    def token_generator(stream: StrStream) -> Iterator['Token']:
        """Generate tokens from a stream of characters."""

        def _pos(start_pos, end_pos):
            return SourceLocation(*zip(start_pos, end_pos))

        try:
            start_pos = stream.position
            char = stream.pop()
            last_blank = True
            while True:
                # print(f'read {char!r}')
                # whitespace_buffer = ''
                npos = start_pos
                while char in WHITESPACE:
                    # print(f'{char!r} is whitespace')
                    if char == '\n':
                        # if last_blank:
                        # print("last line was blank, yielding blankline")
                        yield Token('\n', TokenType.BlankLine, _pos(start_pos, start_pos))
                        # whitespace_buffer = ''
                        # else:
                        #     # print("newline, but last line wasn't blank")
                        #     last_blank = True
                    # else:
                    #     print("not a newline")
                    # else:
                    #     whitespace_buffer += char
                    npos = stream.position
                    char = stream.pop()
                    # print(f'read {char!r}')
                    continue
                if char == '':
                    # print('end of file')
                    break
                start_pos = npos
                last_blank = False

                if char == '/' and not stream.eof:
                    char = stream.pop()
                    if char == '/':
                        buffer = '//'
                        char = stream.pop()
                        while char != '\n':
                            buffer += char
                            end_pos = stream.position
                            if stream.eof:
                                break
                            char = stream.pop()
                        yield Token(buffer, TokenType.Comment, _pos(start_pos, end_pos))
                        last_blank = True
                        start_pos = end_pos
                        continue
                    if char == '*':
                        buffer = '/*'
                        char = stream.pop()
                        while True:
                            buffer += char
                            end_pos = stream.position
                            if stream.eof:
                                break
                            char = stream.pop()
                            if buffer[-2:] == '*/':
                                break
                        yield Token(buffer, TokenType.BlockComment, _pos(start_pos, end_pos))
                        last_blank = True
                        # surround.append(Token(buffer, TokenType.Comment, _pos(start_pos, end_pos)))
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
                    yield Token(buffer, TokenType.String, _pos(start_pos, end_pos))
                    start_pos = npos
                    continue
                elif (tt := TOKEN_REVERSE_MAP.get(char, None)) is not None:
                    yield Token(char, tt, _pos(start_pos, start_pos))
                elif char in TokenType.Operator.value:
                    yield Token(char, TokenType.Operator, _pos(start_pos, start_pos))
                elif char in WORD_START:
                    # Some alphanumeric, let's build up a buffer.
                    buffer = ''
                    last_pos = start_pos
                    npos = start_pos
                    while char in TokenType.Word.value:
                        buffer += char
                        end_pos = last_pos
                        last_pos = stream.position
                        npos = stream.position
                        char = stream.pop()
                    if buffer == 'op' and char in SPECIAL_OPERATORS:
                        t = SPECIAL_OPERATORS[char]
                        while len(buffer) < len(t.value) and char == t.value[len(buffer)]:
                            buffer += char
                            end_pos = last_pos
                            last_pos = stream.position
                            npos = stream.position
                            char = stream.pop()
                        if buffer != t.value:
                            raise ValueError(f"I don't undertsand the token {buffer!r} (expected {t.value}).")
                        yield Token(buffer, TokenType.SpecialOperator, _pos(start_pos, end_pos), special_op_type=t)
                        continue
                    yield Token(buffer, TOKEN_REVERSE_MAP.get(buffer, TokenType.Word), _pos(start_pos, end_pos))
                    start_pos = npos
                    continue
                elif char in NUMBER_START:
                    # Some numeric, let's build up a buffer.
                    buffer = ''
                    last_pos = start_pos
                    while char in TokenType.Number.value:
                        buffer += char
                        last_pos = stream.position
                        end_pos = start_pos
                        char = stream.pop()
                    suffix = ''
                    while True:
                        found = 0
                        for possible_end in NUMBER_END:
                            if suffix == possible_end:
                                found += 1
                                continue
                            if possible_end.startswith(suffix) and char == possible_end[len(suffix):]:
                                found += 1
                                suffix += char
                                end_pos = last_pos
                                char = stream.pop()
                                break
                        if found <= 1:
                            break
                    # if char in NUMBER_END:
                    #     buffer += char
                    #     end_pos = last_pos
                    #     char = stream.pop()
                    yield Token(buffer + suffix, TokenType.Number, _pos(start_pos, end_pos))
                    start_pos = end_pos
                    continue
                else:
                    raise ValueError(f"I don't under stand the character {char!r} at {start_pos}")

                start_pos = stream.position
                char = stream.pop()
        except EOFError:
            yield Token('', TokenType.EOF, _pos(start_pos, start_pos))
