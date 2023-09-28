from typing import Iterable, Iterator, Union, Self
from dataclasses import dataclass, field
from contextlib import contextmanager
from contextvars import ContextVar

from .. import CompilerNotice, MODULE_LOGGER, SourceLocation
from ..lexer import *
from ..typing import StaticType, BUILTINS

_LOG = MODULE_LOGGER.getChild(__name__)


@dataclass(frozen=True, slots=True)
class VariableDecl:
    type: StaticType
    location: SourceLocation


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeContext:
    """Describes a compile-time defined scope."""

    name: str | None = field(kw_only=False)
    variables: dict[str, VariableDecl | Self] = field(default_factory=dict)
    parent: Self | None = field(default=None)
    location: SourceLocation | None = field(default=None)

    @classmethod
    def current(cls) -> Self:
        return _SCOPE.get()

    @classmethod
    @contextmanager
    def new(cls, name: str = None, vars: dict[str, VariableDecl] | None = None) -> Self:
        cur = _SCOPE.get()
        if vars is None:
            vars = {}
        val = ScopeContext(name=name, parent=cur, variables=vars)
        token = _SCOPE.set(val)
        try:
            yield val
        finally:
            _SCOPE.reset(token)

    @classmethod
    @contextmanager
    def enter(cls, name: str = None, location: SourceLocation | None = None) -> Self:
        cur = _SCOPE.get()
        if name in cur.variables:
            val = cur.variables[name]
            if not isinstance(val, ScopeContext):
                raise RuntimeError(f"Cannot enter context {cur.fqdn}.{name}, it is a {type(val).__name__}!")
        else:
            val = ScopeContext(name=name, parent=cur, location=location)
            cur.variables[name] = val
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

    """
    @contextmanager
    def merge(self, other: dict[str, StaticType]):
        cur = _SCOPE.get()
        val = ScopeContext(name=None, parent=cur)
        token = _SCOPE.set(val)
        try:
            _LOG.debug(f"Merging {other} in")
            val.variables.update(other)
            yield val
        finally:
            _SCOPE.reset(token)

    """

    def in_scope(self, identifier: str) -> VariableDecl | None:
        # _LOG.debug(f'Searching for {identifier!r} in {self.fqdn}')
        s = self
        while s:
            if identifier in s.variables:
                return s.variables[identifier]
            s = s.parent


GLOBAL_SCOPE = ScopeContext(None, variables=BUILTINS)
_SCOPE: ContextVar[ScopeContext] = ContextVar('_SCOPE', default=GLOBAL_SCOPE)


def check_program(program: Iterable[Document]):
    for document in program:
        yield from _populate(document)

    print(GLOBAL_SCOPE)

    for document in program:
        yield from _check(document)


from contextlib import ExitStack


def _populate(element: Lex) -> Iterator[CompilerNotice]:
    _LOG.debug(f"Populating static identifiers from {type(element).__name__} into {ScopeContext.current().fqdn}")
    match element:
        case Namespace():
            scope = ScopeContext.current()
            with ExitStack() as ex:
                for name in element.name:
                    if name in scope.variables and not isinstance(scope.variables[name], ScopeContext):
                        extra = None
                        if isinstance(scope.variables[name], VariableDecl):
                            extra = CompilerNotice("Note", f"From here.", scope.variables[name].location)
                        raise CompilerNotice("Error",
                                             f"{name!r} already exists in {scope.fqdn}!",
                                             element.location,
                                             extra=extra)
                    scope = ex.enter_context(ScopeContext.enter(name, location=element.location))
                for decl in element.declarations:
                    yield from _populate(decl)
        case Declaration():
            scope = ScopeContext.current()
            name = element.identity.lhs.value
            if name in scope.variables:
                raise CompilerNotice("Error",
                                     f"{element.identity.lhs.value!r} already defined!",
                                     element.identity.lhs.location,
                                     extra=CompilerNotice("Note", "Here.", scope.variables[name].location))
            if (decl := scope.in_scope(element.identity.lhs.value)):
                yield CompilerNotice("Warning",
                                     f"{element.identity.lhs.value!r} is shadowing an existing identifier!",
                                     element.identity.lhs.location,
                                     extra=CompilerNotice("Note", "Here.", decl.location))
            scope.variables[name] = VariableDecl(StaticType.from_type(element.identity.rhs, scope),
                                                 element.identity.location)
        case Document():
            for decl in element.declarations:
                try:
                    yield from _populate(decl)
                except CompilerNotice as ex:
                    yield ex
        case _:
            yield CompilerNotice('Error', f"Static population for `{type(element).__name__}` is not implemented!",
                                 element.location)
    if False:
        yield


def _check(element: Lex) -> Iterator[CompilerNotice]:
    scope = ScopeContext.current()
    _LOG.debug(f"Checking {type(element).__name__} in {scope.fqdn}")
    match element:
        case Declaration():
            # TODO: check metadata
            try:
                lhs_type = StaticType.from_type(element.identity.rhs, scope)
                _LOG.debug(f"- Declaration lhs type is {lhs_type.name}")
            except CompilerNotice as ex:
                yield ex
            yield from _check(element.identity)
            if element.initial is not None:
                # TODO: extend vars with param names
                with ScopeContext.new(element.identity.lhs.value):
                    yield from _check(element.initial)
        case Namespace():
            scope = ScopeContext.current()
            with ExitStack() as ex:
                for name in element.name:
                    ex.enter_context(ScopeContext.enter(name, location=element.location))
                for decl in element.declarations:
                    yield from _check(decl)
        case Document():
            for decl in element.declarations:
                yield from _check(decl)
        case _:
            yield CompilerNotice('Error', f"Checks for `{type(element).__name__}` are not implemented!",
                                 element.location)
