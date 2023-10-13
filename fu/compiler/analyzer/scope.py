from dataclasses import dataclass, field
from typing import Self, Optional, Union
from contextlib import contextmanager
from contextvars import ContextVar
from logging import getLogger

from .. import SourceLocation

from .static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalyzerScope:
    """Describes a compile-time defined scope."""

    name: str | None = field(kw_only=False)
    members: dict[str, Union[StaticVariableDecl, 'AnalyzerScope']] = field(default_factory=dict)
    scopes: dict[str, 'AnalyzerScope'] = field(init=False, default_factory=dict)
    parent: Self | None = field(default=None, repr=False)
    location: SourceLocation | None = field(default=None)
    return_type: StaticVariableDecl | None = field(default=None)

    @property
    def parsing_builtins(self) -> bool:
        return _PARSING_BUILTINS.get()

    @classmethod
    def current(cls) -> 'AnalyzerScope':
        return _CURRENT_ANALYZER_SCOPE.get()

    @classmethod
    @contextmanager
    def new(cls,
            name: str | None = None,
            vars: dict[str, Union[StaticVariableDecl, 'AnalyzerScope']] | None = None,
            return_type: StaticVariableDecl | None = None):
        cur = _CURRENT_ANALYZER_SCOPE.get()
        if name in cur.scopes:
            raise ValueError(f"Already have {cur.fqdn}.{name}! Use `.enter(...)`.")
        if vars is None:
            vars = {}
        val = AnalyzerScope(name=name, parent=cur, members=vars, return_type=return_type)
        if name is not None:
            cur.scopes[name] = val
        token = _CURRENT_ANALYZER_SCOPE.set(val)
        try:
            yield val
        finally:
            _CURRENT_ANALYZER_SCOPE.reset(token)

    @classmethod
    @contextmanager
    def enter(cls, name: str | None = None, location: SourceLocation | None = None) -> Self:
        cur = _CURRENT_ANALYZER_SCOPE.get()
        if name is None:
            raise RuntimeError('Anonymous scope!')
        if name in cur.scopes:
            val = cur.scopes[name]
            if not isinstance(val, AnalyzerScope):
                raise RuntimeError(f"Cannot enter context {cur.fqdn}.{name}, it is a {type(val).__name__}!")
        else:
            val = AnalyzerScope(name=name, parent=cur, location=location)
            cur.scopes[name] = val
        token = _CURRENT_ANALYZER_SCOPE.set(val)
        try:
            yield val
        finally:
            _CURRENT_ANALYZER_SCOPE.reset(token)

    def get_child(self, name: str) -> Optional['AnalyzerScope']:
        if name not in self.scopes:
            return None
        ret = self.scopes[name]
        if not isinstance(ret, AnalyzerScope):
            raise RuntimeError(f"Cannot enter context {self.fqdn}.{name}, it is a {type(ret).__name__}!")
        return ret

    @property
    def fqdn(self) -> str:
        s: AnalyzerScope | None = self
        r = self.name
        while s is not None:
            s = s.parent
            if s is not None and s.name is not None:
                r = f"{s.name}.{r}"
        return r or '<GLOBAL SCOPE>'

    def in_scope(self, identifier: str) -> Union['AnalyzerScope', StaticVariableDecl, None]:
        # _LOG.debug(f'Searching for {identifier!r} in {self.fqdn}')
        s: AnalyzerScope | None = self
        while s is not None:
            _LOG.debug(f'Searching for {identifier!r} in {self.fqdn} among {set(s.members.keys())}')
            if identifier in s.members:
                ret = s.members[identifier]
                _LOG.debug(f'\tFound {ret}')
                return ret
            s = s.parent
        return None


GLOBAL_SCOPE = AnalyzerScope(None)
_CURRENT_ANALYZER_SCOPE: ContextVar[AnalyzerScope] = ContextVar('_SCOPE', default=GLOBAL_SCOPE)
_PARSING_BUILTINS: ContextVar[bool] = ContextVar('_PARSING_BUILTINS', default=False)
