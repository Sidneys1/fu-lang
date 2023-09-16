from io import TextIOBase
from contextlib import contextmanager
from typing import TypeVar, Generic, ContextManager, Iterable

from . import StrStream as _StrStream, Stream as _Stream


class StrStream(_StrStream):
    WHITESPACE = ' \t\n\r'

    __stream: TextIOBase

    __pos: int
    __line_pos: int
    __line: str

    __committed: bool = False

    def __init__(self, stream: TextIOBase, pos: int = 0, line: str | None = None, line_pos: int = 0):
        self.__pos = pos
        self.__stream = stream
        self.__line = line or stream.readline()
        self.__line_pos = line_pos
        # print(f'created stream {self.__pos=}, {self.__line_pos=}, {self.__line=}')

    @property
    def pos(self):
        return self.__pos

    @property
    def eof(self) -> bool:
        return len(self.__line) == 0

    @property
    def tail(self) -> str:
        return self.__line[self.__line_pos:]

    @contextmanager
    def clone(self):
        pos = self.__stream.tell()
        stream = self.__class__(self.__stream, self.__pos, self.__line, self.__line_pos)
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
            raise EOFError()
        ret = self.__line[self.__line_pos]
        return ret

    def pop(self) -> str:
        if self.eof:
            raise EOFError()
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


class ListStream(Generic[T], _Stream[T, 'ListStream[T]']):
    __list: list[T]
    __index: int
    __committed = False

    def __init__(self, items: list[T], index=0) -> None:
        self.__list = items
        self.__index = index

    @property
    def eof(self) -> bool:
        return self.__index == len(self.__list)

    @contextmanager
    def clone(self):
        clone = self.__class__(self.__list, self.__index)
        try:
            yield clone
        finally:
            if clone.__committed:
                self.__index = clone.__index

    def peek(self) -> T:
        if self.eof:
            raise EOFError()
        print(f'Peek<{self.__list[self.__index]}>')
        return self.__list[self.__index]

    def pop(self) -> T:
        if self.eof:
            raise EOFError()
        self.__index += 1
        print(f'Pop<{self.__list[self.__index - 1]}>')
        return self.__list[self.__index - 1]

    def commit(self) -> None:
        self.__committed = True
