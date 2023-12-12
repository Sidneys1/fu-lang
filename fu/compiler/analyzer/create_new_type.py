from logging import getLogger
from typing import Iterator

from ...types import ComposedType, GenericType, IntegralType, ThisType, TypeBase, InterfaceType, RefType  #, StaticType
from .. import CompilerNotice
from ..analyzer.resolvers import resolve_type
from ..analyzer.scope import AnalyzerScope
from ..analyzer.static_type import type_from_lex
from ..analyzer.static_variable_decl import StaticVariableDecl
from ..lexer import *

_LOG = getLogger(__package__)


def create_new_type(decl: TypeDeclaration, outer_scope: AnalyzerScope) -> Iterator[CompilerNotice]:
    """Create a new type from a lexical `TypeDeclaration`."""
    extra = ''
    if decl.generic_params is not None:
        extra = '<' + ', '.join(x.value for x in decl.generic_params.params) + '>'

    _LOG.debug(f"Creating new type `{decl.name.value}{extra}`.")
    assert not (decl.definition is None or isinstance(decl.definition, Type_))
    this = ThisType()
    this_decl = StaticVariableDecl(this, decl)
    scope_members: dict[str, StaticVariableDecl] = {}
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
        scope_members[x.value] = StaticVariableDecl(g, x)

    members: dict[str, StaticVariableDecl] = {}

    with AnalyzerScope.new(decl.name.value, AnalyzerScope.Type.Type, vars=scope_members, this_decl=this_decl) as scope:
        inherits: list[TypeBase] = []
        errors = False
        special_operators: dict[SpecialOperatorType, tuple[tuple[TypeBase, ...], TypeBase]] = {}
        for element in decl.definition:
            match element:
                case Declaration(identity=Identity(lhs=Identifier(value='this'))):
                    # Inerhitance
                    if element.initial is not None:
                        yield CompilerNotice('Error', "Inheritance `this: <type>` cannot have an assignment.",
                                             element.initial.location)
                        continue
                    if any(isinstance(x, (ParamList, ArrayDef)) for x in element.identity.rhs.mods):
                        yield CompilerNotice('Error', "Types cannot inherit from functions or arrays.",
                                             element.identity.rhs.location)
                        errors = True
                        continue
                    if any(isinstance(x, GenericType.GenericParam) for x in element.identity.rhs.mods):
                        yield CompilerNotice('Error', "Types cannot inherit directly from generic parameters.",
                                             element.identity.rhs.location)
                        errors = True
                        # input(f"can't inherit `{element.identity.rhs}`")
                        continue

                    try:
                        base = resolve_type(element.identity.rhs)
                    except CompilerNotice as ex:
                        yield ex
                        continue

                    assert isinstance(base, ComposedType)
                    if isinstance(base, IntegralType):
                        yield CompilerNotice('Error', "Types cannot inherit from integral types.",
                                             element.identity.rhs.location)
                        errors = True
                        # input(f"can't inherit `{element.identity.rhs}`")
                        continue
                    _LOG.debug(f"Ineriting `{base.name}` ({type(base).__name__}) in `{scope.fqdn}`.")
                    if isinstance(base, InterfaceType):
                        # Interface membership will be checked at _check time
                        inherits.append(base)
                        continue
                    # Add members from base
                    for m, t in base.instance_members.items():
                        if m in scope.members:
                            # input(f"interface `{scope.name}` already has a member `{m}`!")
                            yield CompilerNotice('Error',
                                                 f"`{scope.name}` already has a member named `{m}`.",
                                                 element.location,
                                                 extra=[
                                                     CompilerNotice('Note',
                                                                    "Defined here.",
                                                                    location=this_decl.member_decls[m].location)
                                                 ])
                            errors = True
                            continue
                        # this.members[m] = t
                        svd = StaticVariableDecl(t, element)
                        members[m] = svd
                        scope.members[m] = svd
                        this_decl.member_decls[m] = svd  # TODO: sorta
                    inherits.append(base)
                    continue
                case Declaration(identity=SpecialOperatorIdentity()):
                    assert isinstance(element.identity, SpecialOperatorIdentity)
                    scope = AnalyzerScope.current()
                    name = element.identity.lhs
                    if name.value in scope.members:
                        # TODO: something something overloads
                        yield CompilerNotice('Error',
                                             f"Special operator `{name}` already implemented for type `{scope.name}`.",
                                             element.location)
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
                    _LOG.debug(f"Adding `{name}` to type `{scope.fqdn}` as `{t.name}`.")
                    svd = StaticVariableDecl(t, element)
                    scope.members[name.value] = svd
                    # members[name.value] = svd
                    # this.members[name.value] = t
                    # this_decl.member_decls[name.value] = svd
                    special_operators[name] = t.callable
                    continue
                case Declaration(identity=Identity()):
                    name = element.identity.lhs.value
                    if name in scope.members:
                        yield CompilerNotice('Error',
                                             f"Identifier `{name}` already defined for type.",
                                             element.location,
                                             extra=[CompilerNotice('Note', "Here.", scope.members[name].location)])
                        continue
                    elif (d := scope.in_scope(element.identity.lhs.value)):
                        yield CompilerNotice("Warning",
                                             f"{element.identity.lhs.value!r} is shadowing an existing identifier!",
                                             element.identity.lhs.location,
                                             extra=[CompilerNotice("Note", "Here.", d.location)])

                    try:
                        var_type = type_from_lex(element.identity.rhs, scope)
                    except CompilerNotice as ex:
                        yield ex
                        continue

                    if not element.is_fat_arrow and element.initial is not None and not isinstance(
                            element.initial, (Scope, ExpList)):
                        try:
                            rhs_type = resolve_type(element.initial, want=var_type)
                        except CompilerNotice as ex:
                            yield ex
                        else:
                            # if isinstance(var_type, StaticType) and rhs_type == var_type.underlying:
                            #     var_type = var_type.underlying
                            if var_type != rhs_type:
                                allowed = yield from _check_conversion(rhs_type, var_type, element.initial.location)
                                if not allowed:
                                    continue
                    # Add to current scope

                    _LOG.debug(f"Adding {name} to {scope.fqdn} as {var_type.name}")
                    # input()
                    svd = StaticVariableDecl(var_type,
                                             element,
                                             fqdn=(scope.fqdn + '.' + name) if scope.parent is not None else name)
                    scope.members[name] = svd
                    members[name] = svd
                    if scope.this_decl is not None:
                        scope.this_decl.member_decls[name] = svd
                case TypeDeclaration():
                    raise CompilerNotice("Error", "Nested types aren't currently supported.", element.location)

                case _:
                    raise NotImplementedError(f"Don't know how to do `{element}`")
                # case Declaration():
                #     raise NotImplementedError(f"Don't know how to create from {elems}")
            # from . import _populate
            # input(f"Populating from {element}")
            # yield from _populate(element)

        if errors:
            _LOG.warning('Aborting type creation: there were errors!')
            return

        for k, v in scope.members.items():
            if isinstance(v, StaticScope):
                raise NotImplementedError("Nested type scopes??")

        # TODO: calc size

        if decl.generic_params:
            new_type = GenericType(
                decl.name.value,
                # size=None,
                #    reference_type=True,
                inherits=inherits,
                instance_members={
                    k: v.type
                    for k, v in members.items()
                },
                special_operators=special_operators,
                generic_params=generic_params)
        else:
            new_type = ComposedType(
                decl.name.value,
                # size=None,
                # reference_type=True,
                inherits=inherits,
                instance_members={
                    k: v.type
                    for k, v in members.items()
                },
                special_operators=special_operators)
        # input(f"Resolving this of {new_type.name}")
        this.resolve(new_type)

        _debug_type(new_type)

        # input(new_type)
        outer_scope.members[decl.name.value] = StaticVariableDecl(new_type,
                                                                  decl,
                                                                  member_decls={**this_decl.member_decls})


def _debug_type(new_type: GenericType | ComposedType) -> None:
    _LOG.debug(f"New type: `{new_type.name}`")
    size = new_type.get_size()
    _LOG.debug(f"\tSize: {size if size is not None else '???'}")
    slots: list[str] = []
    tot = 0
    known = True
    for k, v in new_type.instance_members.items():
        size: int
        tname: str
        pos = f"{tot:#04x}" if known else '0x??'
        if isinstance(v, GenericType.GenericParam):
            _LOG.debug(f"\t * {pos} `.{k}: {v.name}`: Generic Parameter, Unknown Size ")
            known = False
            continue

        if isinstance(v, ComposedType):
            size = RefType.get_size()
            tname = f'ref<{v.name}>'
        else:
            tname = v.name
            size = v.get_size()

        sz = tot % size
        if sz:
            sz = size - sz
            div = sz * 2
            pname = '--'
            if len(pname) > div:
                pname = pname[:-2] + '..'
            cname = pname.rjust(int(div + 0.5) // 2 + (len(pname) // 2)).ljust(div)
            slots.append(cname)
            _LOG.debug(f"\t * {pos} - {sz} bytes of alignment padding -")
            tot += sz
            pos = f"{tot:#04x}" if known else '0x??'

        aname = '.' + k
        _LOG.debug(f"\t * {pos} `{aname}: {tname}`:\t{size}")

        tot += size
        div = size * 2
        if len(aname) > div:
            aname = aname[:-2] + '..'
        cname = aname.rjust(int(div + 0.5) // 2 + (len(aname) // 2)).ljust(div)
        slots.append(cname)
    if known:
        _LOG.debug(f"\t |{'|'.join(slots)}|")
    # input()
