from io import TextIOBase
from contextlib import contextmanager
from typing import TypeVar, Generic, Any

from . import StrStream as _StrStream, Stream as _Stream
from .tokenizer import TokenType, Token


class StrStream(_StrStream):
    WHITESPACE = ' \t\n\r'

    __stream: TextIOBase

    __pos: int
    __line_pos: int
    __line: str
    __depth: int = 0
    __line_no: int
    __peeked: int = 0
    __popped: int = 0

    __committed: bool = False

    def __init__(self,
                 stream: TextIOBase,
                 pos: int = 0,
                 line: str | None = None,
                 line_pos: int = 0,
                 line_no: int = 1,
                 depth: int = 0):
        self.__pos = pos
        self.__stream = stream
        self.__line = line or stream.readline()
        self.__line_pos = line_pos
        self.__line_no = line_no
        self.__depth = depth
        # print(f'created stream {self.__pos=}, {self.__line_pos=}, {self.__line=}')

    @property
    def position(self) -> tuple[int, int, int]:
        return self.__pos, self.__line_no, self.__line_pos + 1

    @property
    def depth(self) -> int:
        return self.__depth

    @property
    def pos(self):
        return self.__pos

    @property
    def eof(self) -> bool:
        return len(self.__line) == 0

    @property
    def tail(self) -> str:
        if self.eof:
            return None
        return self.__line[self.__line_pos:]

    @contextmanager
    def clone(self):
        pos = self.__stream.tell()
        stream = self.__class__(self.__stream, self.__pos, self.__line, self.__line_pos, self.__line_no,
                                self.__depth + 1)
        try:
            yield stream
        finally:
            if not stream.__committed:
                self.__stream.seek(pos)
                self.__peeked += stream.__peeked
                return
            self.__pos = stream.__pos
            self.__line = stream.__line
            self.__line_pos = stream.__line_pos
            self.__peeked += stream.__peeked
            self.__popped += stream.__popped

    def peek(self) -> str:
        self.__peeked += 1
        if self.eof:
            return None
        ret = self.__line[self.__line_pos]
        print('peek', ret)
        return ret

    def pop(self) -> str:
        # self.__peeked += 1
        self.__popped += 1
        if self.eof:
            return None
        ret = self.__line[self.__line_pos]
        self.__pos += 1
        self.__line_pos += 1
        if self.__line_pos == len(self.__line):
            self.__line = self.__stream.readline()
            self.__line_pos = 0
            self.__line_no += 1
        print('pop', ret)
        return ret

    def commit(self) -> None:
        if self.__committed:
            raise ValueError()
        self.__committed = True

    def consume_whitespace(self) -> None:
        while not self.eof and self.peek() in self.WHITESPACE:
            self.pop()

    @property
    def efficiency(self) -> tuple[int, int]:
        return self.__peeked, self.__popped


T = TypeVar('T', covariant=True)


class StreamExpectError(Exception):
    expected: Any
    got: Any

    def __init__(self, expected, got):
        self.expected = expected
        self.got = got


class QuietStreamExpectError(Exception):
    ...


class ListStream(Generic[T], _Stream[T, 'ListStream[T]']):
    _list: list[T]
    _index: int
    _committed = False
    _depth: int = 0
    _peeked: int = 0
    _popped: int = 0

    def __init__(self, items: list[T], index=0, depth=0) -> None:
        self._list = items
        self._index = index
        self._depth = depth

    @property
    def eof(self) -> bool:
        return self._index == len(self._list)

    @property
    def depth(self) -> int:
        return self._depth

    @contextmanager
    def clone(self):
        clone = self.__class__(self._list, self._index, self._depth + 1)
        try:
            # print("Clone...")
            yield clone
        finally:
            if clone._committed:
                self._index = clone._index
                self._popped += clone._popped
            self._peeked += clone._peeked
            # print("...Commit")
            # else:
            # print("...Rollback")

    def peek(self) -> T | None:
        self._peeked += 1
        if self.eof:
            return None
        # print(f'Peek<{self.__list[self.__index]}>')
        return self._list[self._index]

    def pop(self) -> T | None:
        # self._peeked += 1
        self._popped += 1
        if self.eof:
            return None
        self._index += 1
        # print(f'Pop<{self.__list[self.__index - 1]}>')
        return self._list[self._index - 1]

    def commit(self) -> None:
        self._committed = True

    @property
    def efficiency(self) -> tuple[int, int]:
        return self._peeked, self._popped


class TokenStream(ListStream[Token]):

    def expect(self, type_: TokenType, quiet=False) -> Token:
        if self.eof:
            raise EOFError()
        peek = self.pop()
        if peek.type_ != type_:
            if quiet:
                raise QuietStreamExpectError(type_, peek)
            raise StreamExpectError(type_, peek)
        return peek
