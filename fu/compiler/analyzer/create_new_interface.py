from logging import getLogger
from typing import Iterator

from ...types import GenericType, InterfaceType, ThisType, TypeBase, IntegralType  #, StaticType
from .. import CompilerNotice
from ..lexer import *
from .resolvers import resolve_type
from .scope import AnalyzerScope
from .static_type import type_from_lex
from .static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


def create_new_interface(decl: TypeDeclaration, outer_scope: AnalyzerScope) -> Iterator[CompilerNotice]:
    extra = ''
    if decl.generic_params is not None:
        extra = '<' + ', '.join(x.value for x in decl.generic_params.params) + '>'

    _LOG.debug(f"Creating new interface `{decl.name.value}{extra}`.")
    assert not (decl.definition is None or isinstance(decl.definition, Type_))
    this = ThisType()
    this_decl = StaticVariableDecl(this, decl)
    vars: dict[str, StaticVariableDecl] = {}
    generic_params: dict[str, GenericType.GenericParam] = {}

    if decl.generic_params is not None and len(set(x.value for x in decl.generic_params.params)) != len(
            decl.generic_params.params):
        raise CompilerNotice('Error', "Generic parameter names must be unique.", decl.generic_params.location)

    for x in decl.generic_params.params if decl.generic_params is not None else ():
        if (outer_type := outer_scope.in_scope(x.value)) is not None:
            yield CompilerNotice('Warning',
                                 f"Generic type `{x.value}` shadows existing `{x.value}`, a `{outer_type.name}`.",
                                 x.location)
        g = GenericType.GenericParam(x.value)
        generic_params[x.value] = g
        vars[x.value] = StaticVariableDecl(g, x)

    with AnalyzerScope.new(decl.name.value, AnalyzerScope.Type.Type, vars=vars, this_decl=this_decl) as scope:
        inherits: list[TypeBase] = []
        errors = False
        special_operators: dict[SpecialOperatorType, tuple[tuple[TypeBase, ...], TypeBase]] = {}
        indexable: tuple[tuple[TypeBase, ...], TypeBase] | None = None
        default_impl_members: set[str] = set()
        for element in decl.definition:
            match element:
                case Declaration(identity=Identity(lhs=Identifier(value='this'))):
                    if element.initial is not None:
                        yield CompilerNotice('Error', "Inheritance `this: <type>` cannot have an assignment.",
                                             element.initial.location)
                        continue
                    if any(isinstance(x, (ParamList, ArrayDef)) for x in element.identity.rhs.mods):
                        yield CompilerNotice('Error', "Interfaces cannot inherit from functions or arrays.",
                                             element.identity.rhs.location)
                        errors = True
                        continue
                    if any(isinstance(x, GenericType.GenericParam) for x in element.identity.rhs.mods):
                        yield CompilerNotice('Error', "Interfaces cannot inherit directly from generic parameters.",
                                             element.identity.rhs.location)
                        errors = True
                        # input(f"can't inherit `{element.identity.rhs}`")
                        continue
                    try:
                        base = resolve_type(element.identity.rhs)
                    except CompilerNotice as ex:
                        yield ex
                        continue
                    assert isinstance(base, TypeBase)
                    if isinstance(base, IntegralType):
                        yield CompilerNotice('Error', "Interfaces cannot inherit from integral types.",
                                             element.identity.rhs.location)
                        errors = True
                        continue
                    _LOG.debug(f"Ineriting `{base.name}` in `{scope.fqdn}`.")
                    # Add members from base
                    for m, t in base.members.items():
                        if m in scope.members:
                            # input(f"interface `{scope.name}` already has a member `{m}`!")
                            yield CompilerNotice('Error',
                                                 f"Interface already has a member named `{m}`.",
                                                 element.location,
                                                 extra=[
                                                     CompilerNotice('Note',
                                                                    "Defined here.",
                                                                    location=this_decl.member_decls[m].location)
                                                 ])
                            errors = True
                            continue
                        # input(f"interface `{scope.name}` is inheriting `{base.name}.{m}`")
                        scope.members[m] = t
                        this.members[m] = t
                        this_decl.member_decls[m] = StaticVariableDecl(t, element)  # TODO: sorta
                    inherits.append(base)
                    continue
                case Declaration(identity=SpecialOperatorIdentity()):
                    assert isinstance(element.identity, SpecialOperatorIdentity)
                    scope = AnalyzerScope.current()
                    special_op_type = element.identity.lhs
                    if special_op_type.value in scope.members:
                        # TODO: something something overloads
                        yield CompilerNotice(
                            'Error',
                            f"Special operator `{special_op_type}` already implemented for interface `{scope.name}`.",
                            element.location)
                        errors = True
                        # input(f"Already have special operator `{element.identity.lhs}`")
                        continue
                    if special_op_type == SpecialOperatorType.Constructor:
                        if not element.identity.rhs.mods or not isinstance(last_mod := element.identity.rhs.mods[-1],
                                                                           ParamList):
                            yield CompilerNotice(
                                'Error', f"`{scope.fqdn}.op=` (constructor) must be callable.",
                                last_mod.location if last_mod is not None else element.identity.rhs.location)
                            errors = True
                            # input(f"op= must be callable (not `{element.identity.rhs}`)")
                            continue
                        ret_type = resolve_type(element.identity.rhs.ident).type
                        if ret_type is not this:
                            yield CompilerNotice(
                                'Error',
                                f"`{scope.fqdn}.op=` (constructor) must return `this` (not `{ret_type.name}`).",
                                element.identity.rhs.ident.location)
                            errors = True
                            # input(f"op= must return `this` (not `{element.identity.rhs.ident}`)")
                        # first_param = None
                        # if not last_mod.params or not isinstance(first_param := last_mod.params[0], Type_) or not (
                        #         first_param.ident.value == 'this' and not first_param.mods):
                        #     yield CompilerNotice(
                        #         'Error', f"`{scope.fqdn}.op=` (constructor) must take `this` as first parameter.",
                        #         first_param.location if first_param is not None else last_mod.location)
                        #     input(f"can't inherit `{element.identity.rhs}`")
                        #     errors = True
                        #     continue
                    # Add to current scope
                    try:
                        t = type_from_lex(element.identity.rhs, scope)
                    except CompilerNotice as ex:
                        yield ex
                        continue

                    _LOG.debug(f"Adding `{special_op_type}` to interface `{scope.fqdn}` as `{t.name}`.")
                    svd = StaticVariableDecl(t, element)
                    scope.members[special_op_type.value] = t
                    this.members[special_op_type.value] = t
                    this_decl.member_decls[special_op_type.value] = svd
                    match special_op_type:
                        case SpecialOperatorType.Constructor:
                            special_operators[special_op_type] = t.callable
                        case SpecialOperatorType.Index:
                            special_operators[special_op_type] = t.callable
                            indexable = t.callable
                    if isinstance(element.initial, Scope):
                        default_impl_members.add(special_op_type.value)
                    continue
                case Declaration(initial=Scope()):
                    default_impl_members.add(element.identity.lhs.value)
                # case TypeDeclaration(initial=None):
                #     raise NotImplementedError(f"Don't know how to create from {elems}")
            from . import _populate
            yield from _populate(element)
        if errors:
            _LOG.warning('Aborting interface creation: there were errors!')
            return
        for k, v in scope.members.items():
            if isinstance(v, StaticScope):
                raise NotImplementedError("Nested interface scopes??")

        members = {k: v for k, v in this.members.items() if not isinstance(v, StaticScope)}
        # default_impl_members = {k for k, v in this.members.items() }

        # TODO: calc size
        new_type = InterfaceType(decl.name.value,
                                 get_size=None,
                                 reference_type=True,
                                 inherits=inherits,
                                 instance_members=members,
                                 special_operators=special_operators,
                                 generic_params=generic_params,
                                 indexable=indexable,
                                 default_impls=default_impl_members)
        this.resolve(new_type)
        outer_scope.members[decl.name.value] = StaticVariableDecl(StaticType.of(new_type),
                                                                  decl,
                                                                  member_decls={**this_decl.member_decls})
