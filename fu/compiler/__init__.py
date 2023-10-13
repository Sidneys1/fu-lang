from typing import Protocol, ContextManager, Generic, TypeVar, TypeAlias, Self, TYPE_CHECKING
from dataclasses import dataclass, field
from contextvars import ContextVar
from logging import getLogger

if TYPE_CHECKING:
    from .tokenizer import Token, TokenType

NAME = __name__
MODULE_LOGGER = getLogger(NAME)

SourceFile: ContextVar[str] = ContextVar('SourceFile', default='<unknown>')


@dataclass(frozen=True, slots=True)
class SourceLocation:
    seek: tuple[int, int]
    lines: tuple[int, int]
    columns: tuple[int, int]
    file: str = field(default_factory=SourceFile.get)

    def __str__(self) -> str:
        if self.lines[0] == self.lines[1]:
            columns = self.columns[0] if self.columns[0] == self.columns[1] else f"{self.columns[0]}-{self.columns[1]}"
            return f"{self.file}:{self.lines[0]}:{columns}"
        return f"{self.file}:{self.lines[0]}:{self.columns[0]} to {self.lines[1]}:{self.columns[1]}"

    @classmethod
    def from_to(cls, start: Self, end: Self) -> Self:
        return cls((start.seek[0], end.seek[1]), (start.lines[0], end.lines[1]), (start.columns[0], end.columns[1]))


class CompilerNotice(Exception):
    level: str
    message: str
    location: SourceLocation | None
    extra: list[Self]

    def __init__(self, level: str, message: str, location: SourceLocation, extra: list[Self] | None = None):
        self.level = level
        self.message = message
        self.location = location
        if extra is None:
            extra = []
        self.extra = extra


T = TypeVar('T', covariant=True)
Tk = TypeVar('Tk', bound='Stream', covariant=True)


class ImmutableStream(Generic[T, Tk], Protocol):
    """A stream that cannot be changed (popped from)."""

    @property
    def eof(self) -> bool:
        """Whether the stream is at its end."""

    @property
    def depth(self) -> int:
        """The depth of recursive stream objects."""

    def peek(self) -> T | None:
        """Peek at the next item in the stream."""

    def clone(self) -> ContextManager[Tk]:
        """Clone this stream (produces a `Stream`)."""

    @property
    def efficiency(self) -> tuple[int, int]:
        """Report the number of peeks and pops of this stream."""


class Stream(ImmutableStream[T, Tk], Protocol):
    """A stream that allows popping/commiting."""

    def pop(self) -> T | None:
        """Pop the next object. Advances the stream head."""

    def commit(self) -> None:
        """
        Commit this stream.
        
        This indicates to the parent stream to advance its head to match this one.
        """


ImmutableStrStream: TypeAlias = ImmutableStream[str, 'StrStream']


class StrStream(Stream[str, 'StrStream'], Protocol):
    """A stream that produces strings."""

    @property
    def tail(self) -> str | None:
        """
        Gets the last line of the file. 
        
        Used to report where parsing failed when not consuming the entire document.
        """

    def consume_whitespace(self) -> None:
        """Consumes any amount of whitespace at the read head."""

    @property
    def position(self) -> tuple[int, int, int]:
        """The current stream position (seek-position, line, column)."""


class TokenStream(Stream['Token', 'TokenStream'], Protocol):
    """A stream of lexical tokens."""

    def expect(self, type_: 'TokenType', quiet=False) -> 'Token':
        """Pop a specific type of Token, raise an exception if it doesn't exist."""


ImmutableTokenStream: TypeAlias = ImmutableStream['Token', TokenStream]
