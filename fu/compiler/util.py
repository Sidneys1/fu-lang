from typing import TypeVar, Iterator, Iterable, TypeGuard, Any, Type, Sequence
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass as _dataclass, field
from functools import update_wrapper, partial

T = TypeVar('T')


@contextmanager
def set_contextvar(var: ContextVar[T], value: T) -> Iterator[T]:
    """Sets a context variable to a value and restores it when done."""
    try:
        reset = var.set(value)
        yield value
    finally:
        var.reset(reset)


def is_sequence_of(s: Sequence[Any], _type: Type[T]) -> TypeGuard[Sequence[T]]:
    return all(isinstance(x, _type) for x in s)
