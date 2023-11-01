from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Sequence, Type, TypeGuard, TypeVar, Generator

T = TypeVar('T')


@contextmanager
def set_contextvar(var: ContextVar[T], value: T) -> Iterator[T]:
    """Sets a context variable to a value and restores it when done."""
    try:
        reset = var.set(value)
        yield value
    finally:
        var.reset(reset)


def is_sequence_of(s: Sequence[Any], _type: Type[T]) -> TypeGuard[Sequence[T]]:  # pragma: no cover
    return all(isinstance(x, _type) for x in s)


def collect_returning_generator[G,R](generator: Generator[G, None, R]) -> tuple[R, list[G]]:
    """Return a tuple of the return value and a list of the elements of a generator."""
    ret: R = None  # noqa
    def _():
        nonlocal ret
        ret = yield from generator
    ret2 = list(_())
    return ret, ret2