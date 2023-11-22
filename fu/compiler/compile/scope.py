from contextlib import contextmanager
from contextvars import Token as ContextVarToken, ContextVar
from typing import ContextManager, Optional, TYPE_CHECKING

from ...types import TypeBase
from ...virtual_machine.bytecode.structures import int_u16

from ..analyzer.scope import _CURRENT_ANALYZER_SCOPE, AnalyzerScope

if TYPE_CHECKING:
    from .dependencies import Dependency

_CURRENT_COMPILE_SCOPE: ContextVar['CompileScope'] = ContextVar('_CURRENT_COMPILE_SCOPE')


class CompileScope(ContextManager):
    name: str
    parent: Optional['CompileScope']
    _reset_tok: ContextVarToken | None = None
    _reset_static_tok: ContextVarToken | None = None
    static_scope: AnalyzerScope
    deps: list['Dependency'] | None = None

    def __init__(self, name: str, root=False):
        self.name = name
        if root:
            self.deps = []
        self.parent = CompileScope.current() if not root else None
        if self.parent is None:
            self.static_scope = AnalyzerScope.current()
        else:
            static_scope = self.parent.static_scope.get_child(name)
            if static_scope is None:
                raise RuntimeError(f"Could not find sub-scope `{name}` under `{self.parent.static_scope.fqdn}`")
            self.static_scope = static_scope
            assert self.static_scope is not None

    def add_dep(self, dep: 'Dependency') -> None:
        if self.parent is None:
            assert self.deps is not None
            self.deps.append(dep)
            return
        parent = self
        while parent.parent is not None:
            parent = parent.parent
        assert parent.deps is not None
        parent.add_dep(dep)

    def __enter__(self):
        self._reset_tok = _CURRENT_COMPILE_SCOPE.set(self)
        self._reset_static_tok = _CURRENT_ANALYZER_SCOPE.set(self.static_scope)
        return self

    def __exit__(self, *args) -> None:
        assert self._reset_tok is not None and self._reset_static_tok is not None
        _CURRENT_COMPILE_SCOPE.reset(self._reset_tok)
        _CURRENT_ANALYZER_SCOPE.reset(self._reset_static_tok)
        self._reset_static_tok = None
        self._reset_tok = None

    @contextmanager
    @staticmethod
    def create_root():
        from ..util import set_contextvar
        assert _CURRENT_COMPILE_SCOPE.get(None) is None
        with set_contextvar(_CURRENT_COMPILE_SCOPE, CompileScope('<ROOT>', True)) as root:
            yield root

    @staticmethod
    def current() -> 'CompileScope':
        ret = _CURRENT_COMPILE_SCOPE.get(None)
        assert ret is not None
        return ret

    @property
    def fqdn(self) -> str:
        names = [self.name]
        p = self.parent
        while p is not None and p.parent is not None:
            names.append(p.name)
            p = p.parent
        return '.'.join(reversed(names))

    @contextmanager
    def enter_recursive(self, *fqdn_parts: str):
        from contextlib import ExitStack
        if fqdn_parts:
            with ExitStack() as es:
                for part in fqdn_parts:
                    last = CompileScope(part)
                    es.enter_context(last)
                yield last
        else:
            yield self


class FunctionScope(CompileScope):
    func_id: int_u16
    args: dict[str, TypeBase]
    locals: dict[str, TypeBase]
    decls: dict[str, TypeBase]
    returns: TypeBase

    def __init__(self,
                 name: str,
                 func_id: int_u16,
                 returns: TypeBase,
                 args: dict[str, TypeBase] | None = None,
                 decls: dict[str, TypeBase] | None = None) -> None:
        super().__init__(name)
        self.func_id = func_id
        self.returns = returns
        self.args = args or {}
        self.decls = decls or {}
        self.locals = {}

    @staticmethod
    def current_fn() -> Optional['FunctionScope']:
        current: CompileScope | None = _CURRENT_COMPILE_SCOPE.get()
        while current is not None and current.parent is not None and not isinstance(current, FunctionScope):
            current = current.parent
        assert current is None or isinstance(current, FunctionScope)
        return current

    def __repr__(self) -> str:
        args = ', '.join(f"{k}: {v.name}" for k, v in self.args.items())
        return f"{self.fqdn}({args})"
