from typing import Protocol, ContextManager, Generic, TypeVar, TypeAlias, Iterator


NAME = __name__

T = TypeVar('T', covariant=True)
Tk = TypeVar('Tk', bound='Stream', covariant=True)
class ImmutableStream(Protocol, Generic[T, Tk]):
    @property
    def eof(self) -> bool: ...
    def peek(self) -> T: ...
    def clone(self) -> ContextManager[Tk]: ...

class Stream(ImmutableStream[T, Tk], Protocol):
    def pop(self) -> T: ...
    def commit(self) -> None: ...

# StrStream: a stream of strings (chars)

ImmutableStrStream: TypeAlias = ImmutableStream[str, 'StrStream']
class StrStream(Stream[str, 'StrStream'], Protocol):
    @property
    def tail(self) -> str: ...
    def consume_whitespace(self) -> None: ...
