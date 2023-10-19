from typing import Iterator
from contextlib import ExitStack

from ...types import BUILTINS
from ...types.composed_types.generic_types.type_ import TypeType

from .. import CompilerNotice
from ..lexer import (Declaration, Document, ExpList, Identity, Lex, Namespace, Scope, StaticScope, Type_,
                     TypeDeclaration)

from . import _LOG

from .resolvers import resolve_type
from .scope import _PARSING_BUILTINS, AnalyzerScope
from .static_type import create_new_type, type_from_lex
from .static_variable_decl import StaticVariableDecl


def _populate(element: Lex) -> Iterator[CompilerNotice]:
    from .checks import _check_conversion

    # _LOG.debug(f"Populating static identifiers from {type(element).__name__} into {ScopeContext.current().fqdn}")
    match element:
        case Namespace():
            scope = AnalyzerScope.current()
            with ExitStack() as ex:
                for ident in element.name:
                    name = ident.value
                    if name in scope.members and not isinstance(scope.members[name], AnalyzerScope):
                        extra = []
                        if isinstance(scope.members[name], StaticVariableDecl):
                            extra.append(CompilerNotice("Note", f"From here.", scope.members[name].location))
                        raise CompilerNotice("Error",
                                             f"{name!r} already exists in {scope.fqdn}!",
                                             element.location,
                                             extra=extra)
                    new_scope = ex.enter_context(AnalyzerScope.enter(name, location=element.location))
                    scope.members[name] = new_scope
                    scope = new_scope
                for decl in element.static_scope:
                    yield from _populate(decl)
        case TypeDeclaration(type='type'):
            scope = AnalyzerScope.current()
            name = element.name.value
            if name in scope.members:
                old_value = scope.members[name]
                raise CompilerNotice("Error",
                                     f"`{name}` already defined.",
                                     element.location,
                                     extra=[CompilerNotice('Note', "Here.", old_value.location)])
            elif (old_value := scope.in_scope(name)) is not None:
                raise CompilerNotice("Warning",
                                     f"`{name}` shadows existing type.",
                                     element.location,
                                     extra=[CompilerNotice('Note', "Here.", old_value.location)])
            if _PARSING_BUILTINS.get() and name in BUILTINS:
                t = BUILTINS[name]
                _LOG.debug(f"Found type definition for builtin `{name}`.")
                scope.members[name] = StaticVariableDecl(t, element)
                return

            if element.definition is None:
                raise CompilerNotice("Error", "Cannot forward-declare types. Please provide an assignment.",
                                     element.location)

            if isinstance(element.definition, Type_):
                scope.members[name] = StaticVariableDecl(type_from_lex(element.definition, scope), element)
            else:
                yield from create_new_type(element, scope)
        case Declaration(identity=Identity()):
            scope = AnalyzerScope.current()
            name = element.identity.lhs.value
            if name in scope.members:
                ...
                # old_type = scope.members[name]
                #         if isinstance(old_type, StaticVariableDecl) and isinstance(old_type.type, CallableType):
                #             this_type = StaticType.from_lex(element.identity.rhs, scope)
                #             if not isinstance(this_type, CallableType):
                #                 raise CompilerNotice("Error",
                #                                      f"{element.identity.lhs.value!r} already defined as a method.",
                #                                      element.identity.lhs.location,
                #                                      extra=[CompilerNotice("Note", "Here.", old_type.location)])
                #             if old_type.type.return_type != this_type.return_type:
                #                 raise CompilerNotice(
                #                     "Error",
                #                     f"{element.identity.lhs.value!r} overload is returning `{this_type.return_type.name}` instead of `{old_type.type.return_type.name}`.",
                #                     element.identity.lhs.location,
                #                     extra=[CompilerNotice("Note", "Here.", old_type.location)])
                #             definitions = [x for x in old_type.overloads] if isinstance(old_type,
                #                                                                         OverloadedMethodDecl) else [old_type]
                #             matching = [x for x in definitions if x == this_type]
                #             if matching:
                #                 raise CompilerNotice("Error",
                #                                      f"{element.identity.lhs.value!r} overload is not unique.",
                #                                      element.identity.lhs.location,
                #                                      extra=[
                #                                          CompilerNotice("Note", "One previous definition.", match.location)
                #                                          for match in matching
                #                                      ])
                #             this_decl = StaticVariableDecl(this_type, element)
                #             if isinstance(old_type, OverloadedMethodDecl):
                #                 # input(f'redefining {scope.fqdn}.{name}: added signature')
                #                 old_type.overloads.append(this_decl)
                #             else:
                #                 scope.members[name] = OverloadedMethodDecl(this_type, element, [this_decl, old_type])
                #             return
                #         else:
                #             # TODO don't do this for callable overloads
                #             raise CompilerNotice("Error",
                #                                  f"{element.identity.lhs.value!r} already defined!",
                #                                  element.identity.lhs.location,
                #                                  extra=[CompilerNotice("Note", "Here.", old_type.location)])
            elif (decl := scope.in_scope(element.identity.lhs.value)):
                yield CompilerNotice("Warning",
                                     f"{element.identity.lhs.value!r} is shadowing an existing identifier!",
                                     element.identity.lhs.location,
                                     extra=CompilerNotice("Note", "Here.", decl.location))

            if _PARSING_BUILTINS.get() and name in BUILTINS:
                _LOG.debug(f"Found definition for builtin `{name}`.")
                var_type = BUILTINS[name]
            else:
                # print(f'\n\n\nxxxx\n\n{element}')
                var_type = type_from_lex(element.identity.rhs, scope)

            if element.initial is not None and not isinstance(element.initial, (Scope, ExpList)):
                rhs_type = resolve_type(element.initial, want=var_type)
                if isinstance(var_type, TypeType) and rhs_type == var_type.underlying:
                    var_type = var_type.underlying
                elif var_type != rhs_type:
                    try:
                        _check_conversion(rhs_type, var_type, element.initial.location)
                    except CompilerNotice as ex:
                        yield ex
            # Add to current scope

            _LOG.debug(f"Adding {name} to {scope.fqdn} as {var_type.name}")
            svd = StaticVariableDecl(var_type, element)
            scope.members[name] = svd
            if scope.this_decl is not None:
                scope.this_decl.member_decls[name] = svd
                scope.this_decl.type.members[name] = var_type
        case Document():
            for decl in element.content:
                # try:
                yield from _populate(decl)
                # except CompilerNotice as ex:
                #     yield ex
        case Scope():
            for content in element.content:
                if not isinstance(content, (Declaration, TypeDeclaration)):
                    continue
                yield from _populate(content)
        case _:  # pragma: no cover
            yield CompilerNotice('Error', f"Static population for `{type(element).__name__}` is not implemented!",
                                 element.location)
    if False:
        yield