from io import TextIOBase
from contextlib import contextmanager
from typing import TypeVar, Generic, Any, Iterator
import inspect
import traceback

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

    def peek(self) -> str:
        if self.eof:
            # print('+ Peek<EOF>')
            return None
        self.__peeked += 1
        ret = self.__line[self.__line_pos]
        # print(f'+ Peek<{ret}>')
        # print('peek', ret)
        return ret

    def pop(self) -> str:
        if self.eof:
            # print('+ Pop<EOF>')
            return None
        # self.__peeked += 1
        self.__popped += 1
        ret = self.__line[self.__line_pos]
        # print(f'+ Pop<{ret}@{self.__line_no}:{self.__line_pos + 1}>')
        self.__pos += 1
        self.__line_pos += 1
        if self.__line_pos == len(self.__line):
            self.__line = self.__stream.readline()
            self.__line_pos = 0
            self.__line_no += 1
        # print('pop', ret)
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
    _generator: Iterator[T] | None

    def __init__(self, items: list[T], index=0, depth=0, generator=None) -> None:
        self._list = items
        self._index = index
        self._depth = depth
        self._generator = generator
        self._try_get_more()

    @property
    def eof(self) -> bool:
        return self._index == len(self._list)

    @property
    def depth(self) -> int:
        return self._depth

    @contextmanager
    def clone(self):
        clone = self.__class__(self._list, self._index, self._depth + 1, self._generator)
        try:
            yield clone
        finally:
            if clone._committed:
                self._index = clone._index
                self._peeked += clone._peeked
                self._popped += clone._popped
            else:
                self._peeked += clone._popped + clone._peeked
                # if clone._popped > 0:
                #     print('clone failed big-time:', clone.efficiency)

    def _try_get_more(self):
        if self._generator is None:
            return
        if self._index != len(self._list):
            return
        try:
            self._list.append(next(self._generator))
        except StopIteration:
            self._generator = None

    _who_called = {}

    def peek(self) -> T | None:
        if self.eof:
            return None
        stack = inspect.stack()[1].frame

        if (caller_class := stack.f_locals.get('self', stack.f_locals.get('cls', None))) is not None:
            if caller_class not in ListStream._who_called:
                ListStream._who_called[caller_class] = 0
            ListStream._who_called[caller_class] += 1

        self._peeked += 1
        ret = self._list[self._index]
        self._try_get_more()
        return ret

    def pop(self) -> T | None:
        if self.eof:
            return None
        # self._peeked += 1
        self._popped += 1
        self._index += 1
        ret = self._list[self._index - 1]
        self._try_get_more()
        # print(f"Popped {ret}")
        return ret

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
        if peek.type != type_:
            if quiet:
                raise QuietStreamExpectError(type_, peek)
            raise StreamExpectError(type_, peek)
        return peek
