from contextlib import ExitStack
from typing import Iterator

from ....types import *
from ... import CompilerNotice
from ...lexer import *
from .. import CHECKED_ELEMENTS, _mark_checked_recursive
from ..resolvers import resolve_owning_type, resolve_type
from ..scope import AnalyzerScope
from ..static_variable_decl import OverloadedMethodDecl, StaticVariableDecl
from ._check_conversion import _check_conversion
from ._check_declaration import _check_declaration
from ._check_interface_declaration import _check_interface_declaration
from ._check_type_alias import _check_type_alias
from ._check_type_declaration import check_type_declaration

_LOG = getLogger(__package__)


def _expand_inherits(type_: TypeBase) -> Iterator[TypeBase]:
    to_expand = [type_]
    already_expanded = []
    # print(f"Expanding inheritance of {type_.name}:")
    while to_expand:
        type_ = to_expand.pop()
        if isinstance(type_, ThisType):
            type_ = type_.resolved
        if isinstance(type_, StaticType):
            raise NotImplementedError(type_.name)
        if type_ in already_expanded:
            continue
        yield type_
        already_expanded.append(type_)
        if type_.inherits:
            for x in type_.inherits:
                # print(f"\t{type_.name} inherits {x.name}")
                to_expand.append(x)

            # raise CompilerNotice(
            #     'Critical',
            #     f"Don't know how to check the intersection of `{','.join(x.name for x in lhs_inherits)}` and `{','.join(x.name for x in rhs_inherits)} ({','.join(x.name for x in common)}??)`",
            #     location)


def _check_infix_operator(element: Operator) -> Iterator[CompilerNotice]:
    yield from _check(element.lhs)
    yield from _check(element.rhs)
    match element.oper.value:
        case _:
            yield CompilerNotice('Note', f"Checks for infix operator {element.oper.value!r} are not implemented!",
                                 element.location)


def _check(element: Lex) -> Iterator[CompilerNotice]:
    scope = AnalyzerScope.current()
    # _LOG.debug(f"Checking {type(element).__name__} in {scope.fqdn}")
    # if element in CHECKED_ELEMENTS:
    #     raise RuntimeError("Element checked more than once!")
    CHECKED_ELEMENTS.append(element)
    match element:
        case Identifier():
            return
        case Declaration():
            yield from _check_declaration(element)
        case TypeDeclaration(type='type', definition=list()):
            try:
                if element.name.value not in scope.scopes:
                    existing = scope.in_scope(element.name.value)
                    if isinstance(existing, StaticVariableDecl):
                        # maybe an alias?
                        if existing.type.is_builtin:
                            # Builtin
                            _mark_checked_recursive(element)
                        else:
                            yield CompilerNotice('Debug', f"Checking a type alias is not implemented yet...",
                                                 element.location)
                        return
                    raise NotImplementedError()

                with AnalyzerScope.enter(element.name.value):
                    # Enter type scope and check.
                    yield from check_type_declaration(element)  #, decl=scope.members.get(element.name.value, None))
            except CompilerNotice as ex:
                yield ex
            # except Exception as ex:
            #     yield CompilerNotice('Critical', f"Unknown error when checking {element!r}: {ex}", element.location)
        case TypeDeclaration(type='type', definition=None):
            # An builtin or an error
            name = element.name.value
            decl = scope.in_scope(name)
            if decl is None or not isinstance(decl, StaticVariableDecl) or not decl.type.is_builtin:
                fqdn = scope.fqdn
                fqdn = (f"{fqdn}.{name}") if fqdn else name
                raise CompilerNotice('Error', f"Type declaration or alias `{fqdn}` is incomplete.", element.location)
        case TypeDeclaration(type='type', definition=Type_()):
            yield from _check_type_alias(element)
        case TypeDeclaration(type='interface', definition=list()):
            try:
                if element.name.value not in scope.scopes:
                    existing = scope.in_scope(element.name.value)
                    if isinstance(existing, StaticVariableDecl):
                        # maybe an alias?
                        if existing.type.is_builtin:
                            # Builtin
                            _mark_checked_recursive(element)
                        else:
                            yield CompilerNotice('Debug', f"Checking a type alias is not implemented yet...",
                                                 element.location)
                        return
                    raise NotImplementedError()

                with AnalyzerScope.enter(element.name.value):
                    yield from _check_interface_declaration(element)
            except CompilerNotice as ex:
                yield ex
        case TypeDeclaration():
            yield CompilerNotice(
                'Note', "Checks for type declarations of form `xxx: "
                f"{element.type}: <{type(element.definition).__name__}>` are not implemented!", element.location)
            return
        case ReturnStatement():
            if element.value is None:
                if scope.return_type.type != VOID_TYPE:
                    yield CompilerNotice('Error',
                                         f"Empty return in a method that returns `{scope.return_type.type.name}`.",
                                         element.location)
                return
            yield from _check(element.value)
            try:
                returned_type = resolve_type(element.value, want=scope.return_type.type)
            except CompilerNotice as ex:
                yield ex
                return
            assert not isinstance(returned_type, StaticScope)
            allowed = yield from _check_conversion(
                returned_type, scope.return_type.type,
                element.value.location if element.value is not None else element.location)
            if not allowed:
                return
                # # TODO: further checks?
                # yield CompilerNotice(
                #     'Error',
                #     f"Return evaluates to a `{returned_type.name}`, but method is defined as returning `{scope.return_type.type.name}`.",
                #     location=element.location,
                #     extra=[CompilerNotice('Note', 'Return type defined here.', location=scope.return_type.location)])
        # case Operator(oper=Token(type=TokenType.Equals)):
        #     raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.LBracket)):
            yield from _check(element.lhs)
            lhs_type = resolve_type(element.lhs)
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            if not lhs_type.indexable:
                yield CompilerNotice('Error', f"`{lhs_type.name}` is not array indexable.", location=element.location)
                return
            # input(f"[{type(element.rhs).__name__}]")
            lhs_expected = lhs_type.indexable[0]
            if isinstance(lhs_expected[0], ThisType):
                lhs_expected = lhs_expected[1:]  # drop 'this'
            # input(f"lhs expected: `{'`,`'.join(x.name for x in lhs_expected)}`")
            match element.rhs:
                case Identifier():
                    rhs_pack = (resolve_type(element.rhs), )
                case LexedLiteral():
                    rhs_pack = (resolve_type(element.rhs, lhs_expected[0]), )
                case _:
                    raise NotImplementedError(f"Got {type(element.rhs).__name__}")
            # input(f"rhs got: `{'`,`'.join(x.name for x in rhs_pack)}`")
            if len(lhs_expected) != len(rhs_pack):
                yield CompilerNotice(
                    'Error',
                    f"Parameter mismatch ({','.join(x.name for x in lhs_expected)}/{','.join(x.name for x in rhs_pack)})",
                    element.rhs.location)
                return

            for l, r in zip(lhs_expected, rhs_pack):
                yield from _check_conversion(r, l, element.rhs.location)
            # if rhs_type != lhs_expected:
            #     names = ', '.join(x.name for x in lhs_expected)
            #     yield CompilerNotice('Error',
            #                          f"`{lhs_type.name}` is not indexable with `{rhs_type.name}` (expected `{names}`).",
            #                          location=element.location)
            #     return
            _mark_checked_recursive(element.rhs)
        case Operator(oper=Token(type=TokenType.Dot)) if element.lhs is not None:
            yield from _check(element.lhs)
            if not isinstance(element.rhs, Identifier):
                yield CompilerNotice('Error',
                                     "The dot operator must have an identifier on the right hand side.",
                                     location=element.rhs.location)
                return
            lhs_type = resolve_type(element.lhs)
            if isinstance(lhs_type, AnalyzerScope):
                if element.rhs.value not in lhs_type.members:
                    yield CompilerNotice('Error',
                                         f"Scope `{lhs_type.name}` does not have a `{element.rhs.value}` member.")
                return
            lhs_decl = None
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            # TODO: check if this is a Type (instance) or a TypeType (static).
            if element.rhs.value not in lhs_type.instance_members:
                # input(f"\n\n\n{lhs_type.name}.{element.rhs.value} not in {lhs_decl.member_decls}")
                yield CompilerNotice('Error',
                                     f"`{lhs_type.name}` does not have a `{element.rhs.value}` member.",
                                     location=element.location)
            _mark_checked_recursive(element.rhs)
        case Operator(oper=Token(type=TokenType.Dot)) if element.lhs is None:
            if not isinstance(element.rhs, Identifier):
                yield CompilerNotice('Error', f"Right hand side of dot operator must be an identifier.",
                                     element.location)
                return
            name = element.rhs.value
            this_type = scope.in_scope('this')
            if this_type is None:
                yield CompilerNotice('Error', f"`this` is not in scope (`.foo` is shorthand for `this.foo`).",
                                     element.location)
                return
            assert isinstance(this_type, StaticVariableDecl)
            assert isinstance(this_type.type, ThisType), f"Expected `ThisType`, got `{type(this_type).__name__}`"

            if name not in this_type.type.resolved.instance_members and name not in this_type.type.resolved.static_members:
                input(this_type.type.resolved)
                yield CompilerNotice('Error', f"`this` (`{this_type.name}`) does not have a member {name!r}.",
                                     element.rhs.location)
                return
            _mark_checked_recursive(element.rhs)
        # case Operator(oper=Token(type=TokenType.Operator)) if element.lhs is None:
        #     """Prefix operator"""
        # case Operator(oper=Token(type=TokenType.Operator)) if element.rhs is None:
        #     """Postfix operator"""
        case Operator(oper=Token(type=TokenType.Operator)):
            """Infix operator"""
            yield from _check_infix_operator(element)
        case Statement():
            yield from _check(element.value)
            warns = []
            eval_type = resolve_type(element.value, warn=lambda x: warns.append(x))
            yield from warns
            if eval_type != VOID_TYPE:
                yield CompilerNotice('Warning', f"`{eval_type.name}` result of statement is discarded?",
                                     element.location)
            # input(f"\n\n`{str(element).strip()}` evals to `{eval_type.name}`")
        case ExpList():
            for x in element.values:
                if isinstance(x, LexedLiteral):
                    _mark_checked_recursive(x)
                else:
                    yield from _check(x)
        case Operator(oper=Token(type=TokenType.LParen)):
            yield from _check(element.lhs)
            if element.rhs is not None:
                yield from _check(element.rhs)

            try:
                type_of_lhs = resolve_type(element.lhs)
            except CompilerNotice as ex:
                yield ex
                return

            decl_lhs: StaticVariableDecl | None = None
            if isinstance(type_of_lhs, StaticVariableDecl):
                decl_lhs = type_of_lhs
                type_of_lhs = type_of_lhs.type
                # input(f"type of {element.lhs} is {type(type_of_lhs).__name__}:{type_of_lhs.name}")

            assert not isinstance(type_of_lhs, StaticScope)

            # input(f"Calling {type_of_lhs}")

            if not (type_of_lhs.callable or isinstance(type_of_lhs, OverloadedMethodDecl)):
                extra = []
                if decl_lhs is not None:
                    extra.append(CompilerNotice('Note', 'Defined here.', location=decl_lhs.location))
                yield CompilerNotice('Error',
                                     f'`{type_of_lhs.name}` is not callable.',
                                     location=element.location,
                                     extra=extra)
                return

            if isinstance(type_of_lhs, OverloadedMethodDecl):
                raise NotImplementedError()
                # if type_of_lhs.match(rhs_params) is None:
                #     yield CompilerNotice('Error', f'Parameter mismatch. Got {rhs_params}', element.rhs.location)
                return

            # if decl_lhs is not None and isinstance(type_of_lhs, StaticType):
            #     underlying = type_of_lhs.underlying
            #     print(f"`{element.lhs}` is a type! We're constructing a `{underlying.name}`!")
            #     assert type_of_lhs.callable[1] == underlying
            #     if isinstance(underlying, GenericType) and any(
            #             isinstance(x, GenericType.GenericParam) for x in underlying.generic_params.values()):
            #         # TODO: generic type deduction?
            #         # still_generic = {
            #         #     k: v
            #         #     for k, v in underlying.generic_params.items() if isinstance(v, GenericType.GenericParam)
            #         # }
            #         # print(f"\tAnd it's still generic on `{'`, `'.join(still_generic.keys())}`!")
            #         # print(f"{','.join(x.name for x in type_of_lhs.callable[0])}")
            #         # ctor_generics = {
            #         #     k: v
            #         #     for k, v in still_generic.items() if any(v is p for p in type_of_lhs.callable[0])
            #         # }
            #         # print(f"\tCtor takes generic params `{'`, `'.join(ctor_generics.keys())}`!")
            #         # input('')
            #         raise NotImplementedError()

            if element.rhs is None:
                if type_of_lhs.callable[0]:
                    yield CompilerNotice(
                        'Error',
                        f"Parameter count mismatch. Expected `({', '.join(x.name for x in type_of_lhs.callable[0])})`",
                        element.location)
                return
            assert isinstance(element.rhs, ExpList)

            if len(type_of_lhs.callable[0]) != len(element.rhs.values):
                yield CompilerNotice(
                    'Error',
                    f"Parameter count mismatch. Expected `({', '.join(x.name for x in type_of_lhs.callable[0])})`",
                    element.location)
                return

            allowed = True
            for lhs_param, rhs_param in zip(type_of_lhs.callable[0], element.rhs.values):
                allowed |= yield from _check_conversion(resolve_type(rhs_param, want=lhs_param), lhs_param,
                                                        rhs_param.location)
            _mark_checked_recursive(element.rhs)
            if not allowed:
                return
                # if lhs_param != rhs_param_type:
                #     yield CompilerNotice(
                #         'Error', f"Parameter mismatch, expected `{lhs_param.name}`, got `{rhs_param_type.name}`.",
                #         rhs_param.location)

        case Operator(oper=Token(type=TokenType.Equals)):
            yield from _check(element.lhs)
            yield from _check(element.rhs)
            try:
                lhs_type_decl, lhs_member_decl = resolve_owning_type(element.lhs)
                rhs_type = resolve_type(element.rhs)
                # input(f'right hand of assignment ({type(element.rhs).__name__}) is {rhs_type.name}')
            except CompilerNotice as ex:
                yield ex
                return
            if lhs_member_decl.const:
                yield CompilerNotice('Error', "Cannot assign to a const variable.", element.location)
            if isinstance(rhs_type, StaticScope):
                yield CompilerNotice('Error', f"Cannot assign a Scope to a `{lhs_member_decl.type.name}`.",
                                     element.location)
                return
            if isinstance(rhs_type, StaticVariableDecl):
                rhs_decl = rhs_type
                rhs_type = rhs_type.type
            allowed = yield from _check_conversion(rhs_type, lhs_member_decl.type, element.location)
            if not allowed:
                return
        case Namespace():
            with ExitStack() as ex:
                for ident in element.name:
                    name = ident.value
                    ex.enter_context(AnalyzerScope.enter(name))
                for decl in element.static_scope:
                    yield from _check(decl)
        case Document():
            for decl in element.content:
                yield from _check(decl)
        case Scope():
            first_return = None
            for content in element.content:
                if isinstance(content, ReturnStatement):
                    if first_return is None:
                        first_return = content
                    else:
                        yield CompilerNotice('Error',
                                             'Functions may only have one top-level return statement.',
                                             location=content.location,
                                             extra=[
                                                 CompilerNotice('Note',
                                                                'First return statement here.',
                                                                location=first_return.location)
                                             ])
                try:
                    yield from _check(content)
                except CompilerNotice as ex:
                    yield ex
                    return
        case Operator():
            yield CompilerNotice(
                'Note',
                f"Checks for `Operator(oper={element.oper},lhs={element.lhs},rhs={element.rhs})` are not implemented!",
                element.location)
        case Atom():
            yield from _check(element.value)
        case LexedLiteral():
            pass
        case IfStatement():
            if element.term is not None:
                _check(element.term)
                # check that term evaluates to a bool
                resolved = resolve_type(element.term, BOOL_TYPE)
                assert not isinstance(resolved, StaticScope)
                if isinstance(resolved, StaticVariableDecl):
                    resovled_decl = resolved
                    resolved = resolved.type
                if resolved != BOOL_TYPE:
                    yield CompilerNotice('Error',
                                         f"`if` term does not evaluate to a `bool` (got `{resolved.name}` instead).",
                                         element.term.location)
            for x in element.content:
                _check(element.content)

        # case Declaration():
        #     yield CompilerNotice(
        #         'Critical', f"Checks for `Declaration(initial={type(element.initial).__name__})` are not implemented!",
        #         element.location)
        case _:
            yield CompilerNotice('Note', f"Checks for `{type(element).__name__}` are not implemented!",
                                 element.location)
