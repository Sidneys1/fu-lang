import sys
import argparse
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


R = TypeVar('R')


def collect_returning_generator(generator: Generator[T, None, R]) -> tuple[R, list[T]]:
    """Return a tuple of the return value and a list of the elements of a generator."""
    ret: R
    ret = None  # type: ignore

    def _():
        nonlocal ret
        ret = yield from generator

    ret2 = list(_())
    return ret, ret2

def set_default_subparser(self, name, args=None, positional_args=0):
    """default subparser selection. Call after setup, just before parse_args()
    name: is the name of the subparser to call by default
    args: if set is the argument list handed to parse_args()

    , tested with 2.7, 3.2, 3.3, 3.4
    it works with 2.6 assuming argparse is installed
    """
    subparser_found = False
    for arg in sys.argv[1:]:
        if arg in ['-h', '--help']:  # global help if no subparser
            break
    else:
        for x in self._subparsers._actions:
            if not isinstance(x, argparse._SubParsersAction):
                continue
            for sp_name in x._name_parser_map.keys():
                if sp_name in sys.argv[1:]:
                    subparser_found = True
        if not subparser_found:
            # insert default in last position before global positional
            # arguments, this implies no global options are specified after
            # first positional argument
            if args is None:
                sys.argv.insert(len(sys.argv) - positional_args, name)
            else:
                args.insert(len(args) - positional_args, name)

argparse.ArgumentParser.set_default_subparser = set_default_subparser
