from typing import Iterator
from logging import getLogger

from ....types import ThisType, ComposedType
from ... import CompilerNotice
from ...lexer import (Declaration, Identity, ParamList, Scope, Type_, Expression, Operator, Atom, LexedLiteral,
                      Identifier)
from .. import _mark_checked_recursive
from .._populate import _populate
from ..scope import AnalyzerScope
from ..static_type import type_from_lex
from ..static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


def _check_declaration(element: Declaration) -> Iterator[CompilerNotice]:
    from . import _check
    scope = AnalyzerScope.current()
    # Check shadowing
    if scope.parent is not None and (outer_decl := scope.parent.in_scope(element.identity.lhs.value)) is not None:
        _LOG.debug(f"`{element.identity.lhs.value}` already defined in `{scope.parent.fqdn}` (checking {scope.fqdn})")
        yield CompilerNotice('Warning',
                             f"Declaration of {element.identity.lhs.value!r} shadows previous declaration.",
                             location=element.identity.location,
                             extra=[CompilerNotice('Note', "Here.", location=outer_decl.location)])
    # Check redefinition
    if (inner_decl := scope.members.get(element.identity.lhs.value, None)) is not None:
        assert isinstance(inner_decl, StaticVariableDecl), f"Was unexpectedly {type(inner_decl).__name__}"
        # TODO: overloaded methods
        # if isinstance(inner_decl, OverloadedMethodDecl):
        #     ...
        # el
        if inner_decl.location is not element.identity.location and not (isinstance(inner_decl.type, ThisType)
                                                                         and scope.type == AnalyzerScope.Type.Type):
            yield CompilerNotice('Error',
                                 f"Redefinition of {element.identity.lhs.value!r}.",
                                 location=element.identity.location,
                                 extra=[CompilerNotice('Note', "Here.", location=inner_decl.location)])

    _mark_checked_recursive(element.identity)

    if element.initial is None:
        return

    try:
        lhs_type = type_from_lex(element.identity.rhs, scope)
    except CompilerNotice as ex:
        yield ex
        return

    if (not element.is_fat_arrow) and (not isinstance(element.initial, Scope)):
        # Not fat arrow and not a scope -> static assignment (not callable)
        yield from _check(element.initial)
        return

    assert isinstance(element.initial,
                      (Scope, Expression, Operator, Atom, LexedLiteral,
                       Identifier)), f"element.initial is unexpectedly a `{type(element.initial).__name__}`"

    if not isinstance(lhs_type, ComposedType) or lhs_type.callable is None:
        raise CompilerNotice("Error", f"`{element.identity}` is not callable but is initialized with a body.",
                             element.identity.location)

    if isinstance(element.initial, Scope) and not element.initial.content:
        yield CompilerNotice('Warning', "Method initialized with an empty body.", element.initial.location)

    params = element.identity.rhs.mods[-1]
    assert isinstance(params, ParamList)
    assert all(not isinstance(p, Type_) or p.ident.value == 'this' for p in params.params)
    props = {
        p.lhs.value: StaticVariableDecl(type_from_lex(p.rhs, AnalyzerScope.current()), p, const=True)
        for p in params.params if isinstance(p, Identity)
    }
    # if element.is_fat_arrow:
    #     input(props)
    with AnalyzerScope.new(element.identity.lhs.value,
                           AnalyzerScope.Type.Function,
                           vars=props,
                           return_type=StaticVariableDecl(lhs_type.callable[1], element)):
        try:
            if isinstance(element.initial, Scope):
                yield from _populate(element.initial)
            # TODO type check return
            yield from _check(element.initial)
        except CompilerNotice as ex:
            yield ex
