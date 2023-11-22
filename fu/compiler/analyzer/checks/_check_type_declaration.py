from typing import Iterator

from ....types import InterfaceType, ThisType, TypeBase, StaticType
from ... import CompilerNotice
from ...lexer import (CompilerNotice, Declaration, Identity, ParamList, ReturnStatement, Scope, SpecialOperatorIdentity,
                      SpecialOperatorType, Type_, TypeDeclaration)
from ...tokenizer import SpecialOperatorType
from .. import CHECKED_ELEMENTS, _mark_checked_recursive
from .._populate import _populate
from ..scope import AnalyzerScope
from ..static_type import type_from_lex
from ..static_variable_decl import StaticVariableDecl, decl_of
from ._assigns_to import _assigns_to


def check_type_declaration(element: TypeDeclaration) -> Iterator[CompilerNotice]:
    assert element.type == 'type'
    scope = AnalyzerScope.current()
    # input(scope)
    _mark_checked_recursive(element.name)

    assert element.definition is not None

    if isinstance(element.definition, Type_):
        _mark_checked_recursive(element.definition)
        return

    original_unassigned: list[StaticVariableDecl] = []
    ctors: list[Declaration] = []
    this_decl = scope.members['this']
    assert isinstance(this_decl.type, ThisType)
    actual_type = this_decl.type.resolved
    if actual_type is None:
        raise CompilerNotice('Critical', f"Got unresolved `this`!", element.location)

    # This will need to include _populate!
    from . import _check
    for elem in element.definition:
        match elem:
            case Declaration(identity=Identity()) if elem.initial is None and elem.identity.lhs.value == 'this':
                # Special case - inheritance
                inherits_decl = decl_of(elem.identity.rhs)
                assert isinstance(inherits_decl.type, StaticType)
                inherits_type = inherits_decl.type.underlying
                if isinstance(inherits_type, InterfaceType):
                    # Type inherits an interface
                    from ._check_satisfies_interface import _check_satisfies_interface
                    err = _check_satisfies_interface(actual_type, inherits_type, elem.location)
                    if err is not None:
                        yield err
                else:
                    # We inherit from another type?
                    raise NotImplementedError()
            case Declaration(identity=SpecialOperatorIdentity(lhs=SpecialOperatorType.Constructor)):
                # special case - constructor (deferred)
                ctors.append(elem)
                continue
            # case Declaration(identity=SpecialOperatorIdentity(lhs=SpecialOperatorType.Index)):
            #     # TODO: check op[]
            #     continue
            case Declaration(identity=Identity()) if elem.initial is None and elem.identity.lhs.value != 'this':
                # Uninitialized things
                assert isinstance(elem.identity, Identity)
                if elem.identity.lhs.value not in this_decl.member_decls:
                    raise CompilerNotice('Error', f"`{elem.identity.lhs.value}` is undefined in `{scope.fqdn}`.",
                                         elem.identity.lhs.location)
                original_unassigned.append(this_decl.member_decls[elem.identity.lhs.value])
            case Declaration():
                CHECKED_ELEMENTS.append(elem)
                _mark_checked_recursive(elem.identity)
                # Fall through - we need to populate!
                # yield from _check(elem.identity)

                if not isinstance(elem.initial, Scope):
                    yield from _check(elem)
                    continue

                # populate scope
                name = elem.identity.lhs.value if isinstance(elem.identity, Identity) else elem.identity.lhs.value
                assert elem.identity.rhs.mods
                params = elem.identity.rhs.mods[-1]
                assert isinstance(params, ParamList)
                elem_type = type_from_lex(elem.identity.rhs, scope)
                assert elem_type.callable is not None
                props = {
                    p.lhs.value: StaticVariableDecl(type_from_lex(p.rhs, AnalyzerScope.current()).as_const(), p)
                    for p in params.params
                    if isinstance(p, Identity) or (isinstance(p, Type_) and p.ident.value != 'this')
                }
                if any(isinstance(p, Type_) and p.ident.value == 'this' for p in params.params):
                    props[
                        'this'] = this_decl  # StaticVariableDecl(this_decl.type, element, member_decls=this_decl.member_decls)
                # scope.this_decl.member_decls[]
                with AnalyzerScope.new(name,
                                       AnalyzerScope.Type.Function,
                                       vars=props,
                                       this_decl=this_decl,
                                       return_type=StaticVariableDecl(elem_type.callable[1], elem)):
                    # input(f"Populating {func_scope.fqdn}")
                    yield from _populate(elem.initial)
                    yield from _check(elem.initial)
                continue
        yield from _check(elem)

    if not ctors:
        if original_unassigned:
            inner = '`, `'.join(x.lex.identity.lhs.value for x in original_unassigned)
            yield CompilerNotice(
                'Warning', f"Type `{scope.fqdn}` has uninitialized members: `{inner}`. Consider adding a constructor?",
                element.location)
        return

    for ctor in ctors:
        unassigned = list(original_unassigned)
        assert ctor.initial is not None and isinstance(ctor.initial, Scope)
        params = ctor.identity.rhs.mods[-1]
        assert isinstance(params, ParamList)

        props = {
            p.lhs.value: StaticVariableDecl(type_from_lex(p.rhs, AnalyzerScope.current()).as_const(), p)
            for p in params.params if isinstance(p, Identity) or (isinstance(p, Type_) and p.ident.value != 'this')
        }
        # input(f"constructor props are `{'`, `'.join(v.name for v in props.values())}`")
        # input(f"Constructor props: {params.params} -> {props.keys()}")
        this_type = this_decl.type
        if isinstance(this_type, StaticType):
            this_type = this_type.underlying
        assert isinstance(this_type, TypeBase), f"`this` was unexpectedtly a `{type(this_type).__name__}`."
        props['this'] = StaticVariableDecl(this_type, element, member_decls=this_decl.member_decls)
        assert isinstance(ctor.initial, Scope)
        # input(f"scope:\n\n{scope.scopes.keys()}")
        with AnalyzerScope.new(ctor.identity.lhs.value,
                               AnalyzerScope.Type.Function,
                               vars=props,
                               this_decl=props['this']):
            CHECKED_ELEMENTS.append(ctor)
            # yield from _check(ctor.initial)
            CHECKED_ELEMENTS.append(ctor.initial)
            # TODO: check that all params are being used
            _mark_checked_recursive(ctor.identity)
            for x in ctor.initial.content:
                match x:
                    case ReturnStatement() if x.value is not None:
                        yield CompilerNotice('Error', "Returning values not allowed in a constructor!", x.location)
                    case Declaration():
                        yield from _check(x)
                    case _:
                        yield from _check(x)
                        # try:
                        for assigns_to in _assigns_to(x):
                            if assigns_to in unassigned:
                                unassigned.remove(assigns_to)
                            # except CompilerNotice as ex:
                            #     yield ex
            # _mark_checked_recursive(ctor)
        if unassigned:
            inner = '`, `'.join(x.lex.identity.lhs.value for x in unassigned)
            yield CompilerNotice('Warning', f"Constructor for `{scope.fqdn}` does not initialize members `{inner}`.",
                                 ctor.initial.location)
