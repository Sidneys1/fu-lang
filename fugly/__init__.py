from typing import Protocol, ContextManager, Generic, TypeVar, TypeAlias, Self
from dataclasses import dataclass, field
from contextvars import ContextVar
from logging import getLogger

NAME = __name__
MODULE_LOGGER = getLogger(NAME)

SourceFile: ContextVar[str | None] = ContextVar('SourceFile', default=None)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    seek: tuple[int, int]
    lines: tuple[int, int]
    columns: tuple[int, int]
    file: str = field(default_factory=SourceFile.get)

    def __str__(self) -> str:
        if self.lines[0] == self.lines[1]:
            columns = self.columns[0] if self.columns[0] == self.columns[1] else f"{self.columns[0]}-{self.columns[1]}"
            return f"{self.file}, line {self.lines[0]}:{columns}"
        return f"{self.file}, lines {self.lines[0]}:{self.columns[0]} to {self.lines[1]}:{self.columns[1]}"

    @classmethod
    def from_to(cls, start: Self, end: Self) -> Self | None:
        if start is None or end is None:
            return
        return cls((start.seek[0], end.seek[1]), (start.lines[0], end.lines[1]), (start.columns[0], end.columns[1]))


class CompilerNotice(Exception):
    level: str
    message: str
    location: SourceLocation
    extra: Self | None = None

    def __init__(self, level: str, message: str, location: SourceLocation, extra: Self | None = None):
        self.level = level
        self.message = message
        self.location = location
        self.extra = extra


T = TypeVar('T', covariant=True)
Tk = TypeVar('Tk', bound='Stream', covariant=True)


class ImmutableStream(Protocol, Generic[T, Tk]):

    @property
    def eof(self) -> bool:
        ...

    @property
    def depth(self) -> int:
        ...

    def peek(self) -> T | None:
        ...

    def clone(self) -> ContextManager[Tk]:
        ...

    @property
    def position(self) -> tuple[int, int, int]:
        ...


class Stream(ImmutableStream[T, Tk], Protocol):

    def pop(self) -> T | None:
        ...

    def commit(self) -> None:
        ...

    @property
    def efficiency(self) -> tuple[int, int]:
        ...


# StrStream: a stream of strings (chars)

ImmutableStrStream: TypeAlias = ImmutableStream[str, 'StrStream']


class StrStream(Stream[str, 'StrStream'], Protocol):

    @property
    def tail(self) -> str | None:
        ...

    def consume_whitespace(self) -> None:
        ...
