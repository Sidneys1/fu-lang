from typing import Any
from dataclasses import dataclass

from . import StaticType


@dataclass(frozen=True, slots=True, kw_only=True)
class CompileTimeSurrogate(StaticType):
    """Represents a Type, resolved at compile-time, that is callable at compile-time."""

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        kwargs = (', ' + ', '.join(k + '=' + v for k, v in kwds.items())) if kwds else ''
        input(f"COMPILE TIME, YO: {self.name}({', '.join(repr(r) for r in args)}{kwargs})")
