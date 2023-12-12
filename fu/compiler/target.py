from contextvars import ContextVar
from enum import StrEnum
from itertools import product
from typing import Iterable
from dataclasses import dataclass
from logging import getLogger

from ..types import (TypeBase, RefType, INT_TYPE, UINT_TYPE, SIZE_TYPE, USIZE_TYPE)

_LOG = getLogger(__package__)


class Architecture(StrEnum):
    NONE = 'none'
    X64 = 'x86_64'

    # ARM = 'arm'

    def platform_size(self, t: TypeBase | type[TypeBase]) -> int:
        if isinstance(t, type):
            if t == RefType and self in (Architecture.NONE, Architecture.X64):
                return 8
            raise NotImplementedError()

        assert t.intrinsic_size() is None
        if self in (Architecture.NONE, Architecture.X64) and t in (SIZE_TYPE, USIZE_TYPE):
            return 8

        if self in (Architecture.NONE, Architecture.X64) and t in (INT_TYPE, UINT_TYPE):
            return 4

        raise NotImplementedError()


class Platform(StrEnum):
    NONE = 'none'
    WINDOWS = 'windows'
    LINUX = 'linux'


# class Runtime(StrEnum):
#     NONE = 'none'
#     MSVC = 'msvc'
#     GNU = 'gnu'
#     MUSL = 'musl'

# WINDOWS_RUNTIMES = (Runtime.NONE, Runtime.MSVC)
# LINUX_RUNTIMES = (Runtime.NONE, Runtime.GNU, Runtime.MUSL)


@dataclass(frozen=True, slots=True)
class Target:
    architecture: Architecture
    platform: Platform

    @classmethod
    def from_string(cls, string: str) -> 'Target':
        arch, plat = string.rsplit('-', maxsplit=1)
        return Target(Architecture[arch], Platform[plat])

    @classmethod
    def known_targets(cls) -> Iterable['Target']:
        yield from (Target(arch, Platform.NONE) for arch in Architecture)
        yield from (Target(*x) for x in product(Architecture, (Platform.WINDOWS, )))
        yield from (Target(*x) for x in product(Architecture, (Platform.LINUX, )))

    @classmethod
    def determine(cls) -> 'Target':
        import platform
        match platform.machine():
            case 'AMD64' | 'x86_64':
                arch = Architecture.X64
            case a:
                _LOG.warning("Could not determine target architecture from Python's "
                             f"`platform.machine() = {a!r}`. Selecting 'none'.")
                arch = Architecture.NONE

        match platform.system():
            case 'Windows':
                plat = Platform.WINDOWS
            case 'Linux':
                plat = Platform.LINUX
            case a:
                _LOG.warning("Could not determine target system from Python's "
                             f"`platform.system() = {a!r}`. Selecting 'none'.")
                plat = Platform.NONE

        return Target(arch, plat)

    def __repr__(self) -> str:
        return f"Target(a={self.architecture.value!r}, p={self.platform.value!r})"

    def __str__(self) -> str:
        return '-'.join((self.architecture.value, self.platform.value))


TARGET: ContextVar[Target] = ContextVar('TARGET')
