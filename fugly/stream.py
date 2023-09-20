from io import TextIOBase
from contextlib import contextmanager
from typing import TypeVar, Generic, Any

from . import StrStream as _StrStream, Stream as _Stream


class StrStream(_StrStream):
    WHITESPACE = ' \t\n\r'

    __stream: TextIOBase

    __pos: int
    __line_pos: int
    __line: str
    __depth: int = 0

    __committed: bool = False

    def __init__(self, stream: TextIOBase, pos: int = 0, line: str | None = None, line_pos: int = 0, depth: int = 0):
        self.__pos = pos
        self.__stream = stream
        self.__line = line or stream.readline()
        self.__line_pos = line_pos
        self.__depth = depth
        # print(f'created stream {self.__pos=}, {self.__line_pos=}, {self.__line=}')

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
        stream = self.__class__(self.__stream, self.__pos, self.__line, self.__line_pos, self.__depth + 1)
        try:
            yield stream
        finally:
            if not stream.__committed:
                self.__stream.seek(pos)
                return
            self.__pos = stream.__pos
            self.__line = stream.__line
            self.__line_pos = stream.__line_pos

    def peek(self) -> str:
        if self.eof:
            return None
        ret = self.__line[self.__line_pos]
        return ret

    def pop(self) -> str:
        if self.eof:
            return None
        ret = self.__line[self.__line_pos]
        self.__pos += 1
        self.__line_pos += 1
        if self.__line_pos == len(self.__line):
            self.__line = self.__stream.readline()
            self.__line_pos = 0
        return ret

    def commit(self) -> None:
        if self.__committed:
            raise ValueError()
        self.__committed = True

    def consume_whitespace(self) -> None:
        while not self.eof and self.peek() in self.WHITESPACE:
            self.pop()


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
    __list: list[T]
    __index: int
    __committed = False
    __depth: int = 0

    def __init__(self, items: list[T], index=0, depth=0) -> None:
        self.__list = items
        self.__index = index
        self.__depth = depth

    @property
    def eof(self) -> bool:
        return self.__index == len(self.__list)

    @property
    def depth(self) -> int:
        return self.__depth

    @contextmanager
    def clone(self):
        clone = self.__class__(self.__list, self.__index, self.__depth + 1)
        try:
            # print("Clone...")
            yield clone
        finally:
            if clone.__committed:
                self.__index = clone.__index
                # print("...Commit")
            # else:
            # print("...Rollback")

    def peek(self) -> T | None:
        if self.eof:
            return None
        # print(f'Peek<{self.__list[self.__index]}>')
        return self.__list[self.__index]

    def pop(self) -> T | None:
        if self.eof:
            return None
        self.__index += 1
        # print(f'Pop<{self.__list[self.__index - 1]}>')
        return self.__list[self.__index - 1]

    def expect(self, type_: type[T], quiet=False) -> T:
        if self.eof:
            raise EOFError()
        if not isinstance(peek := self.__list[self.__index], type_):
            if quiet:
                raise QuietStreamExpectError(type_, peek)
            raise StreamExpectError(type_, peek)
        return self.pop()

    def commit(self) -> None:
        self.__committed = True
