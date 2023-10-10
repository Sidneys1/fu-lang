from dataclasses import dataclass, field
from typing import Self
from contextlib import contextmanager
from contextvars import ContextVar
from logging import getLogger

from .. import SourceLocation

from .static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


@dataclass(frozen=True, slots=True, kw_only=True)
class StaticScope:
    """Describes a compile-time defined scope."""

    name: str | None = field(kw_only=False)
    members: dict[str, StaticVariableDecl | Self] = field(default_factory=dict)
    parent: Self | None = field(default=None, repr=False)
    location: SourceLocation | None = field(default=None)
    return_type: StaticVariableDecl | None = field(default=None)

    @property
    def parsing_builtins(self) -> bool:
        return _PARSING_BUILTINS.get()

    @classmethod
    def current(cls) -> Self:
        return _SCOPE.get()

    @classmethod
    @contextmanager
    def new(cls,
            name: str = None,
            vars: dict[str, StaticVariableDecl] | None = None,
            return_type: StaticVariableDecl | None = None):
        cur = _SCOPE.get()
        if vars is None:
            vars = {}
        val = StaticScope(name=name, parent=cur, members=vars, return_type=return_type)
        token = _SCOPE.set(val)
        try:
            yield val
        finally:
            _SCOPE.reset(token)

    @classmethod
    @contextmanager
    def enter(cls, name: str = None, location: SourceLocation | None = None) -> Self:
        cur = _SCOPE.get()
        if name in cur.members:
            val = cur.members[name]
            if not isinstance(val, StaticScope):
                raise RuntimeError(f"Cannot enter context {cur.fqdn}.{name}, it is a {type(val).__name__}!")
        else:
            val = StaticScope(name=name, parent=cur, location=location)
            cur.members[name] = val
        token = _SCOPE.set(val)
        try:
            yield val
        finally:
            _SCOPE.reset(token)

    @property
    def fqdn(self) -> str:
        s = self
        r = self.name
        while s is not None:
            s = s.parent
            if s is not None and s.name is not None:
                r = f"{s.name}.{r}"
        return r or '<GLOBAL SCOPE>'

    def in_scope(self, identifier: str) -> Self | StaticVariableDecl | None:
        _LOG.debug(f'Searching for {identifier!r} in {self.fqdn}')
        s = self
        while s:
            _LOG.debug(f'Searching for {identifier!r} in {self.fqdn} among {set(s.members.keys())}')
            if identifier in s.members:
                ret = s.members[identifier]
                _LOG.debug(f'\tFound {ret}')
                return ret
            s = s.parent


GLOBAL_SCOPE = StaticScope(None)
_SCOPE: ContextVar[StaticScope] = ContextVar('_SCOPE', default=GLOBAL_SCOPE)
_PARSING_BUILTINS: ContextVar[bool] = ContextVar('_PARSING_BUILTINS', default=False)