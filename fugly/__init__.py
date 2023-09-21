from typing import Protocol, ContextManager, Generic, TypeVar, TypeAlias, Iterator
from dataclasses import dataclass

NAME = __name__


@dataclass(frozen=True, slots=True)
class TokenPosition:
    seek: tuple[int, int]
    lines: tuple[int, int]
    columns: tuple[int, int]

    def __str__(self) -> str:
        if self.lines[0] == self.lines[1]:
            columns = self.columns[0] if self.columns[0] == self.columns[1] else f"{self.columns[0]}-{self.columns[1]}"
            return f"{self.lines[0]}:{columns}"
        return f"{self.lines[0]}:{self.columns[0]} to {self.lines[1]}:{self.columns[1]}"


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
