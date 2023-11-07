from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum, auto
from logging import getLogger
from typing import Optional, Self, Union

from .. import SourceLocation
from ...types import BOOL_TYPE
from .static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalyzerScope:
    """Describes a compile-time defined scope."""

    class Type(Enum):
        """What type a given analyzer scope is."""
        Anonymous = auto()
        Generic = auto()
        Function = auto()
        Namespace = auto()
        Type = auto()

    name: str | None = field(kw_only=False)
    type: Type = field(kw_only=False)
    members: dict[str, Union[StaticVariableDecl, 'AnalyzerScope']] = field(default_factory=dict)
    scopes: dict[str, 'AnalyzerScope'] = field(init=False, default_factory=dict)
    parent: Self | None = field(default=None, repr=False)
    location: SourceLocation | None = field(default=None)
    return_type: StaticVariableDecl | None = field(default=None)
    this_decl: StaticVariableDecl | None = field(default=None)

    @property
    def parsing_builtins(self) -> bool:
        return _PARSING_BUILTINS.get()

    @classmethod
    def current(cls) -> 'AnalyzerScope':
        return _CURRENT_ANALYZER_SCOPE.get()

    @classmethod
    def new_global_scope(cls) -> 'AnalyzerScope':
        assert _CURRENT_ANALYZER_SCOPE.get(None) is None
        ret = cls(None, AnalyzerScope.Type.Anonymous)
        return ret

    @classmethod
    @contextmanager
    def new(cls,
            name: str | None = None,
            type_: Type | None = None,
            vars: dict[str, Union[StaticVariableDecl, 'AnalyzerScope']] | None = None,
            this_decl: StaticVariableDecl | None = None,
            return_type: StaticVariableDecl | None = None):
        if type_ is None:
            raise RuntimeError()
        cur = _CURRENT_ANALYZER_SCOPE.get()
        if name in cur.scopes:
            raise ValueError(f"Already have {cur.fqdn}.{name}! Use `.enter(...)`.")
        if vars is None:
            vars = {}
        if this_decl is not None:
            if 'this' in vars:
                assert vars['this'] == this_decl
            else:
                vars['this'] = this_decl

        val = AnalyzerScope(name=name,
                            type=type_,
                            parent=cur,
                            members=vars,
                            return_type=return_type,
                            this_decl=this_decl)
        if name is not None:
            cur.scopes[name] = val
        token = _CURRENT_ANALYZER_SCOPE.set(val)
        try:
            yield val
        finally:
            _CURRENT_ANALYZER_SCOPE.reset(token)

    @classmethod
    @contextmanager
    def enter(cls, name: str) -> Self:
        cur = _CURRENT_ANALYZER_SCOPE.get()
        if name not in cur.scopes:
            raise RuntimeError(f"Cannot enter {cur.fqdn}.{name}, it doesn't exist!")
        val = cur.scopes[name]
        if not isinstance(val, AnalyzerScope):
            raise RuntimeError(f"Cannot enter context {cur.fqdn}.{name}, it is a {type(val).__name__}!")
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
        _LOG.debug(f'Searching for {identifier!r} in {self.fqdn}')
        s: AnalyzerScope | None = self
        while s is not None:
            _LOG.debug(f'Searching for {identifier!r} in {self.fqdn} among {set(s.members.keys())}')
            if identifier in s.members:
                ret = s.members[identifier]
                _LOG.debug(f'\tFound {ret.name}')
                return ret
            s = s.parent
        return None


_CURRENT_ANALYZER_SCOPE: ContextVar[AnalyzerScope] = ContextVar('_SCOPE')
_PARSING_BUILTINS: ContextVar[bool] = ContextVar('_PARSING_BUILTINS', default=False)


@contextmanager
def set_global_scope(scope: AnalyzerScope):
    """Set the global static analysis scope."""
    assert scope.name is None
    assert _CURRENT_ANALYZER_SCOPE.get(None) is None
    reset = _CURRENT_ANALYZER_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_ANALYZER_SCOPE.reset(reset)
