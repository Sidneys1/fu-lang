from typing import Iterator
from logging import getLogger

from ...types.composed_types import ComposedType
from ...types.integral_types import IntegralType
from ...types import ThisType, TypeBase, TypeType
from ...types.composed_types.generic_types import GenericType
from ...types.composed_types.generic_types.array import ARRAY_TYPE

from .. import CompilerNotice
from ..lexer import (Declaration, Identifier, SpecialOperatorIdentity, SpecialOperatorType, StaticScope, Type_,
                     ParamList, ArrayDef, Identity, TypeDeclaration, GenericParamList)

# from . import _LOG, _populate
from .scope import AnalyzerScope
from .resolvers import resolve_type
from .static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


def type_from_lex(type_: Type_, scope: AnalyzerScope) -> TypeBase:
    """Construct a static type from a lexical type."""
    _LOG.debug(f"Constructing static type from `{type_}`.")
    existing = scope.in_scope(type_.ident.value)
    if existing is None:
        raise CompilerNotice('Error',
                             f"Type `{type_.ident.value}` has not been defined.",
                             location=type_.ident.location)
    assert not isinstance(existing, AnalyzerScope)
    assert isinstance(existing.type, TypeBase)
    actual_type = existing.type
    if isinstance(actual_type, TypeType):
        actual_type = actual_type.underlying
    if type_.mods:
        return _with_modifiers(actual_type, list(type_.mods), scope)
    return actual_type


def _with_modifiers(t: TypeBase, mods: list[ParamList | ArrayDef | GenericParamList], scope: AnalyzerScope) -> TypeBase:
    """Recursively apply modifiers."""
    assert isinstance(t, TypeBase), f"{t} was not `TypeBase`, instead {type(t).__name__}"
    ret: TypeBase | None = t
    while mods:
        mod = mods.pop(0)
        match mod:
            case ArrayDef():
                ret = ARRAY_TYPE.resolve_generic_instance({'T': ret})
            case ParamList():
                params = tuple(
                    type_from_lex(x.rhs if isinstance(x, Identity) else x, scope) for x in mod.params
                    if isinstance(x, Type_) or x.rhs != 'namespace')
                add = '(' + ', '.join(x.name for x in params) + ')'
                ret = TypeBase(ret.name + add, size=None, callable=(params, t))
            case GenericParamList():
                # assert isinstance(ret, )
                assert isinstance(ret, GenericType), f"Expected Generic Type, got {type(ret).__name__} `{ret.name}`"
                param_types: dict[str, TypeBase] = {}
                for i, (k, v) in enumerate(ret.generic_params.items()):
                    if i >= len(mod.params):
                        break
                    x = mod.params[i]
                    x_type = scope.in_scope(x.value)
                    if isinstance(x_type, StaticVariableDecl):
                        x_decl = x_type
                        x_type = x_type.type
                    if x_type is None:
                        x_type = GenericType.GenericParam(x.value)
                    param_types[k] = x_type
                new_type = ret.resolve_generic_instance(param_types)
                assert not isinstance(new_type, GenericType) or all(not isinstance(x, GenericType)
                                                                    for x in new_type.generic_params.values())
                ret = new_type
            case _:
                raise NotImplementedError(f"Don't know how to apply modifier {mod}!")
    return ret


def create_new_type(decl: TypeDeclaration, outer_scope: AnalyzerScope) -> Iterator[CompilerNotice]:
    extra = ''
    if decl.generic_params is not None:
        extra = '<' + ', '.join(x.value for x in decl.generic_params.params) + '>'
    _LOG.debug(f"Creating new type `{decl.name.value}{extra}`.")
    assert not (decl.definition is None or isinstance(decl.definition, Type_))
    this = ThisType()
    vars: dict[str, StaticVariableDecl] = {'this': StaticVariableDecl(this, decl)}
    generic_params: dict[str, GenericType.GenericParam] = {}
    if decl.generic_params is not None and len(set(x.value for x in decl.generic_params.params)) != len(
            decl.generic_params.params):
        raise CompilerNotice('Error', "Generic parameter names must be unique.", decl.generic_params.location)
    for x in decl.generic_params.params if decl.generic_params is not None else ():
        if (outer_type := outer_scope.in_scope(x.value)) is not None:
            yield CompilerNotice(
                'Warning', f"Generic type `{x.value}` shadows existing `{x.value}`, a `{outer_type.name}`.".x.location)
        g = GenericType.GenericParam(x.value)
        generic_params[x.value] = g
        vars[x.value] = StaticVariableDecl(g, x)

    with StaticScope.new(decl.name.value, vars=vars) as scope:
        inherits: list[TypeBase] = []
        errors = False
        special_operators: dict[SpecialOperatorType, tuple[tuple[TypeBase, ...], TypeBase]] = {}
        for element in decl.definition:
            match element:
                case Declaration(identity=Identity(lhs=Identifier(value='this'))):
                    if element.initial is not None:
                        yield CompilerNotice('Error', f"Inheritance `this: <type>` cannot have an assignment.",
                                             element.initial.location)
                        continue
                    if any(isinstance(x, (ParamList, ArrayDef)) for x in element.identity.rhs.mods):
                        yield CompilerNotice('Error', f"Types cannot inherit from functions or arrays.",
                                             element.identity.rhs.location)
                        errors = True
                        # input(f"can't inherit `{element.identity.rhs}`")
                        continue
                    if any(isinstance(x, GenericType.GenericParam) for x in element.identity.rhs.mods):
                        yield CompilerNotice('Error', f"Types cannot inherit directly from generic parameters.",
                                             element.identity.rhs.location)
                        errors = True
                        # input(f"can't inherit `{element.identity.rhs}`")
                        continue
                    base = scope.in_scope(element.identity.rhs.ident.value)
                    assert isinstance(base, StaticVariableDecl)
                    if isinstance(base.type, IntegralType):
                        yield CompilerNotice('Error', f"Types cannot inherit from integral types.",
                                             element.identity.rhs.location)
                        errors = True
                        # input(f"can't inherit `{element.identity.rhs}`")
                        continue
                    _LOG.debug(f"Ineriting `{t.name}` in `{scope.fqdn}`.")
                    inherits.append(base.type)
                    continue
                case Declaration(identity=SpecialOperatorIdentity()):
                    assert isinstance(element.identity, SpecialOperatorIdentity)
                    scope = StaticScope.current()
                    name = element.identity.lhs
                    if name.value in scope.members:
                        # TODO: something something overloads
                        yield CompilerNotice('Error',
                                             f"Special operator `{name}` already implemented for type `{scope.name}`.")
                        errors = True
                        # input(f"Already have special operator `{element.identity.lhs}`")
                        continue
                    if name == SpecialOperatorType.Constructor:
                        if not element.identity.rhs.mods or not isinstance(last_mod := element.identity.rhs.mods[-1],
                                                                           ParamList):
                            yield CompilerNotice(
                                'Error', f"`{scope.fqdn}.op=` (constructor) must be callable.",
                                last_mod.location if last_mod is not None else element.identity.rhs.location)
                            errors = True
                            # input(f"op= must be callable (not `{element.identity.rhs}`)")
                            continue
                        ret_type = resolve_type(element.identity.rhs.ident).type
                        if ret_type != this:
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
                    t = type_from_lex(element.identity.rhs, scope)
                    _LOG.debug(f"Adding `{name}` to type `{scope.fqdn}` as `{t.name}`.")
                    scope.members[name.value] = StaticVariableDecl(t, element)
                    special_operators[name] = t.callable
                    continue
                # case Declaration():
                #     raise NotImplementedError(f"Don't know how to create from {elems}")
                # case TypeDeclaration(initial=None):
                #     raise NotImplementedError(f"Don't know how to create from {elems}")
            yield from _populate(element)
        if errors:
            _LOG.warn('Aborting type creation: there were errors!')
            return
        for k, v in scope.members.items():
            if isinstance(v, StaticScope):
                raise NotImplementedError("Nested type scopes??")

        members = {k: v.type for k, v in scope.members.items() if not isinstance(v, StaticScope) and k != 'this'}
        # TODO: calc size
        if decl.generic_params:
            new_type = GenericType(decl.name.value,
                                   size=None,
                                   reference_type=True,
                                   inherits=inherits,
                                   members=members,
                                   special_operators=special_operators,
                                   generic_params=generic_params)
        else:
            new_type = ComposedType(decl.name.value,
                                    size=None,
                                    reference_type=True,
                                    inherits=inherits,
                                    members=members,
                                    special_operators=special_operators)
        this.resolve(new_type)
        outer_scope.members[decl.name.value] = StaticVariableDecl(TypeType.of(new_type),
                                                                  decl,
                                                                  member_decls={
                                                                      k: v
                                                                      for k, v in scope.members.items() if k != 'this'
                                                                  })
