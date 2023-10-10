from dataclasses import dataclass, field
from logging import getLogger
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Any, Callable

from ..lexer import *
from ..analyzer.static_scope import GLOBAL_SCOPE
from ..analyzer.static_variable_decl import StaticVariableDecl
from ..typing import CallableType

_LOG = getLogger(__name__)
"""
initial stack: [(ref args)]
initial heap: [args]
"""


@dataclass(slots=True)
class RuntimeObject:
    ...


@dataclass(slots=True)
class RuntimeArray(RuntimeObject):
    inner: list[Any]

    def __getitem__(self, value: int) -> Any:
        return self.inner[value]

    def __str__(self):
        return str(self.inner)

    @property
    def length(self) -> int:
        return len(self.inner)


@dataclass(slots=True)
class RuntimeCallable(RuntimeObject):
    inner: Callable

    def __call__(self, *args) -> Any:
        return self.inner(*args)


@dataclass(frozen=True, slots=True, kw_only=True)
class StackFrame:
    params: dict[str, Any] = field(default_factory=list)
    locals: dict[str, Any] = field(init=False, default_factory=dict)

    @classmethod
    @contextmanager
    def call(cls, *, params: list[Any] = None) -> Self:
        if params is None:
            params = []

        try:
            new_stack_frame = cls(params=params)
            reset_token = CurrentStackFrame.set(new_stack_frame)
            yield new_stack_frame
        finally:
            CurrentStackFrame.reset(reset_token)


CurrentStackFrame: ContextVar['StackFrame'] = ContextVar('CurrentStackFrame', default=StackFrame())


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeContext:
    parent: Self | None = field(kw_only=False)
    locals: dict[str, Any] = field(default_factory=dict)

    def get_value(self, name: str):
        scope = self
        while scope is not None:
            if name in scope.locals:
                return scope.locals[name]
            scope = scope.parent
        raise RuntimeError(f"`{name}` does not appear to be defined.")

    @contextmanager
    def call(self, locals: dict[str, Any]) -> Self:
        try:
            new_runtime_context = RuntimeContext(self, locals=locals)
            reset_token = CurrentRuntimeContext.set(new_runtime_context)
            yield new_runtime_context
        finally:
            CurrentRuntimeContext.reset(reset_token)


CurrentRuntimeContext: ContextVar['RuntimeContext'] = ContextVar('CurrentRuntimeContext',
                                                                 default=RuntimeContext(parent=None))


def evaluate(main: StaticVariableDecl, argv: list[str] = None):
    if argv is None:
        argv = []
    assert isinstance(main.type, CallableType)
    params = main.lex.identity.rhs.mods[-1]
    assert isinstance(params, ParamList)
    context = CurrentRuntimeContext.get()
    for k, v in GLOBAL_SCOPE.members.items():
        context.locals[k] = v
    context.locals['print'] = RuntimeCallable(print)
    ret = _evaluate_method(main, params=[RuntimeArray([RuntimeArray(x) for x in argv])])
    from sys import stderr
    print(f'$ `main` returned `{ret}`.', file=stderr)


def _evaluate_statement(element: Lex) -> Any:
    _LOG.debug(f"Evaluating `{str(element).replace('\n', ' ')}`.")
    scope = CurrentRuntimeContext.get()
    match element:
        case Statement():
            return _evaluate_statement(element.value)
        case Literal(type=TokenType.Number):
            return int(element.value)
        case Literal(type=TokenType.String):
            return RuntimeArray(element.value)
        case Identifier():
            return scope.get_value(element.value)
        case Operator(oper=Token(type=TokenType.Dot)):
            lhs = _evaluate_statement(element.lhs)
            assert isinstance(element.rhs, Identifier)
            rhs = element.rhs.value
            from ..analyzer import StaticScope
            match lhs:
                case RuntimeObject():
                    if not hasattr(lhs, rhs):
                        raise TypeError(f"`{type(lhs).__name__}` does not have property {rhs!r}!")
                    return getattr(lhs, rhs)
                case StaticScope():
                    ret = lhs.in_scope(rhs)
                    if ret is None:
                        raise TypeError(f"`{type(lhs).__name__}` does not have property {rhs!r}!")
                    return ret
                case _:
                    raise NotImplementedError(f"Don't know how to dot-operator on `{type(lhs).__name__}`!")
        case Operator(oper=Token(type=TokenType.LParen)):
            lhs = _evaluate_statement(element.lhs)
            if element.rhs is None:
                params = []
            else:
                assert isinstance(element.rhs, ExpList)
                params = [_evaluate_statement(ex) for ex in element.rhs.values]
            match lhs:
                case RuntimeCallable():
                    return lhs(*params)
                case StaticVariableDecl():
                    return _evaluate_method(lhs, params)
                case _:
                    raise NotImplementedError(f"Don't know how to call a `{type(lhs).__name__}`!")
        case Operator(oper=Token(type=TokenType.LBracket)):
            lhs = _evaluate_statement(element.lhs)
            match lhs:
                case RuntimeObject():
                    if not hasattr(lhs, '__getitem__'):
                        raise TypeError(f"`{type(lhs).__name__}` is not indexable!")
                    return lhs[_evaluate_statement(element.rhs)]
                case _:
                    raise NotImplementedError(f"Don't know how to dot-operator on `{type(lhs).__name__}`!")
        case ReturnStatement():
            if element.value is not None:
                return _evaluate_statement(element.value)
            return
        case _:
            raise RuntimeError(f"Don't know how to evaluate `{type(element).__name__}`!")


def _evaluate_method(method: StaticVariableDecl, params: list[Any]):
    param_list = method.lex.identity.rhs.mods[-1]
    assert isinstance(param_list, ParamList)
    assert isinstance(method.type, CallableType)
    assert all(isinstance(x, Identity) for x in param_list.params)
    param_dict = {id.lhs.value: params[i] for i, id in enumerate(param_list.params)}
    param_str = ', '.join(f"{k}={v}" for k, v in param_dict.items())
    _LOG.debug(f"Calling method `{method.lex.identity.lhs.value}` with ({param_str}).")
    with StackFrame.call(params=params), CurrentRuntimeContext.get().call(param_dict):
        stack = CurrentStackFrame.get()
        scope = CurrentRuntimeContext.get()
        # _LOG.debug(f"{stack}\n{scope}")
        for x in method.lex.initial.content:
            val = _evaluate_statement(x)
            if val is not None:
                return val
