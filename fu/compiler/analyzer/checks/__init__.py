from contextlib import ExitStack
from typing import Iterator

from ....types import *

from ... import CompilerNotice
from ...lexer import *

from .. import _mark_checked_recursive, CHECKED_ELEMENTS
from .._populate import _populate
from ..scope import AnalyzerScope
from ..static_variable_decl import OverloadedMethodDecl, StaticVariableDecl
from ..static_type import type_from_lex
from ..resolvers import resolve_type

from ._assigns_to import _assigns_to


def _check_type_declaration(element: TypeDeclaration) -> Iterator[CompilerNotice]:
    assert element.type == 'type'
    scope = AnalyzerScope.current()
    _mark_checked_recursive(element.name)

    if element.definition is None:
        return

    if isinstance(element.definition, Type_):
        _mark_checked_recursive(element.definition)
        return

    unassigned: list[StaticVariableDecl] = []
    ctor: Declaration | None = None
    this_decl = scope.members['this']
    for elem in element.definition:
        match elem:
            case TypeDeclaration():
                yield from _check_type_declaration(elem)
                continue
            case Declaration(identity=SpecialOperatorIdentity(lhs=SpecialOperatorType.Constructor)):
                ctor = elem
                continue
            case Declaration(identity=Identity()) if elem.initial is None:
                assert isinstance(elem.identity, Identity)
                # input(this_decl)
                unassigned.append(this_decl.member_decls[elem.identity.lhs.value])
        yield from _check(elem)

    if ctor is None:
        if unassigned:
            inner = '`, `'.join(x.lex.identity.lhs.value for x in unassigned)
            yield CompilerNotice(
                'Warning', f"Type `{scope.fqdn}` has uninitialized members: `{inner}`. Consider adding a constructor?",
                element.location)
        return

    assert ctor.initial is not None and isinstance(ctor.initial, Scope)
    params = ctor.identity.rhs.mods[-1]
    assert isinstance(params, ParamList)

    props = {
        p.lhs.value: StaticVariableDecl(type_from_lex(p.rhs, StaticScope.current()).as_const(), p)
        for p in params.params if isinstance(p, Identity) or (isinstance(p, Type_) and p.ident.value != 'this')
    }
    # input(f"Constructor props: {params.params} -> {props.keys()}")
    this_type = this_decl.type
    if isinstance(this_type, TypeType):
        this_type = this_type.underlying
    assert isinstance(this_type, TypeBase), f"`this` was unexpectedtly a `{type(this_type).__name__}`."
    props['this'] = StaticVariableDecl(this_type, element, member_decls=this_decl.member_decls)
    assert isinstance(ctor.initial, Scope)
    with StaticScope.new(ctor.identity.lhs.value, vars=props):
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
        yield CompilerNotice(
            'Warning', f"Type `{scope.fqdn}` has uninitialized members: `{inner}`. Consider adding a constructor?",
            element.location)


def _check_declaration(element: Declaration) -> Iterator[CompilerNotice]:
    scope = AnalyzerScope.current()
    # Check shadowing
    if scope.parent is not None and (outer_decl := scope.parent.in_scope(element.identity.lhs.value)) is not None:
        yield CompilerNotice('Warning',
                             f"Declaration of {element.identity.lhs.value!r} shadows previous declaration.",
                             location=element.identity.lhs.location,
                             extra=[CompilerNotice('Note', "Here.", location=outer_decl.location)])
    # Check redefinition
    if (inner_decl := scope.members.get(element.identity.lhs.value, None)) is not None:
        # TODO: overloaded methods
        # if isinstance(inner_decl, OverloadedMethodDecl):
        #     ...
        # el
        if inner_decl.location is not element.identity.location:
            # input(f'{type(inner_decl).__name__}')
            yield CompilerNotice('Error',
                                 f"Redefinition of {element.identity.lhs.value!r}.",
                                 location=element.identity.lhs.location,
                                 extra=[CompilerNotice('Note', "Here.", location=inner_decl.location)])

    _mark_checked_recursive(element.identity)

    if element.initial is not None:
        try:
            lhs_type = type_from_lex(element.identity.rhs, scope)
        except CompilerNotice as ex:
            yield ex
            return
        if not isinstance(element.initial, Scope):
            yield from _check(element.initial)
            return

        if lhs_type.callable is None:
            raise CompilerNotice(
                "Error",
                f"Type of {element.identity.lhs.value!r} is not callable ({lhs_type}) but is initialized with a body.",
                element.identity.location)
        elif not element.initial.content:
            yield CompilerNotice('Warning', "Method initialized with an empty body.", element.initial.location)

        params = element.identity.rhs.mods[-1]
        assert isinstance(params, ParamList)
        props = {
            p.lhs.value: StaticVariableDecl(type_from_lex(p.rhs, AnalyzerScope.current()).as_const(), p)
            for p in params.params
        }

        with AnalyzerScope.new(element.identity.lhs.value,
                               vars=props,
                               return_type=StaticVariableDecl(lhs_type.callable[1], element)):
            try:
                yield from _populate(element.initial)
                # TODO type check return
                yield from _check(element.initial)
            except CompilerNotice as ex:
                yield ex


def _check_conversion(from_: TypeBase | StaticVariableDecl, to_: TypeBase | StaticVariableDecl,
                      location: SourceLocation):
    """
    Check implicit conversion compatiblity in converting `from_` to `to_`.
    
    Reaises a `CompilerNotice` if there are warnings (e.g., narrowing) or errors (conversion not allowed).
    """

    from_decl = None
    if isinstance(from_, StaticVariableDecl):
        from_decl = from_
        from_ = from_.type
    to_decl = None
    if isinstance(to_, StaticVariableDecl):
        to_decl = to_
        to_ = to_.type

    if from_ == to_:
        return

    if VOID_TYPE in (from_, to_):
        raise CompilerNotice('Error', "There are no conversions to or from void.", location=location)

    if from_ == BOOL_TYPE or to_ == BOOL_TYPE:
        raise NotImplementedError('Implicit bool conversions are not yet checked.')
    if isinstance(from_, EnumType) or isinstance(to_, EnumType):
        raise CompilerNotice('Error', "There are no implicit conversions of Enums.", location=location)

    match from_, to_:
    # case (TypeBase(size=None), _) | (_, TypeBase(size=None)):
    #     raise NotImplementedError(f"Can't compare types with unknown sizes ({from_.name} and/or {to_.name})...")
        case IntType(), IntType() if from_.size is not None and to_.size is not None:
            from_min, from_max = from_.range()
            to_min, to_max = to_.range()
            if (from_min < to_min) or (from_max > to_max):
                raise CompilerNotice(
                    'Warning',
                    f"Narrowing when implicitly converting from a `{from_.name}` ({from_.size*8}bit {'' if from_.signed else 'un'}signed) to a `{to_.name}` ({to_.size*8}bit {'' if to_.signed else 'un'}signed).",
                    location=location)
        case FloatType(), IntType():
            raise CompilerNotice('Warning',
                                 f"Loss of precision converting from a `{from_.name}` to a `{to_.name}`.",
                                 location=location)
        case FloatType(), FloatType():
            if to_.exp_bits < from_.exp_bits:
                raise CompilerNotice(
                    'Warning',
                    f"Loss of floating point precision converting from a `{from_.name}` to a `{to_.name}`.",
                    location=location)
        case _, _:
            raise NotImplementedError(
                f"Implicit conversion check of `{from_.name}` to `{to_.name}` is not implemented.")


def _check_infix_operator(element: Operator) -> Iterator[CompilerNotice]:
    yield from _check(element.lhs)
    yield from _check(element.rhs)
    match element.oper.value:
        case '+':
            # input(f"{element.lhs} + {element.rhs}")
            ...
        case _:
            yield CompilerNotice('Note', f"Checks for infix operator {element.oper.value!r} are not implemented!",
                                 element.location)


def _check(element: Lex) -> Iterator[CompilerNotice]:
    scope = AnalyzerScope.current()
    # _LOG.debug(f"Checking {type(element).__name__} in {scope.fqdn}")
    if element in CHECKED_ELEMENTS:
        raise RuntimeError("Element checked more than once!")
    CHECKED_ELEMENTS.append(element)
    match element:
        case Identifier():
            return
        case Declaration(identity=Identity()):
            yield from _check_declaration(element)
        case TypeDeclaration(type='type'):
            try:
                # vars = {'this': scope.members[element.name.value]}
                # if element.generic_params is not None:
                #     for x in element.generic_params.params or ():
                #         vars[x.value] = StaticVariableDecl(GenericType.GenericParam(x.value), x)
                with AnalyzerScope.enter(element.name.value):
                    yield from _check_type_declaration(element)
            except CompilerNotice as ex:
                yield ex
            # except Exception as ex:
            #     yield CompilerNotice('Critical', f"Unknown error when checking {element!r}: {ex}", element.location)
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
                assert not isinstance(returned_type, StaticScope)
                try:
                    _check_conversion(returned_type, scope.return_type.type,
                                      element.value.location if element.value is not None else element.location)
                except CompilerNotice as ex:
                    yield ex
                    return
                # # TODO: further checks?
                # yield CompilerNotice(
                #     'Error',
                #     f"Return evaluates to a `{returned_type.name}`, but method is defined as returning `{scope.return_type.type.name}`.",
                #     location=element.location,
                #     extra=[CompilerNotice('Note', 'Return type defined here.', location=scope.return_type.location)])
            except CompilerNotice as ex:
                yield ex
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
            rhs_type = resolve_type(element.rhs)
            lhs_expected = lhs_type.indexable[0]
            try:
                _check_conversion
            except CompilerNotice as ex:
                yield ex
                return
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
            lhs_decl = None
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            if element.rhs.value not in lhs_type.members:
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
            if name not in this_type.type.members:
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

            for lhs_param, rhs_param in zip(type_of_lhs.callable[0], element.rhs.values):
                rhs_param_type = resolve_type(rhs_param, want=lhs_param)
                if lhs_param != rhs_param_type:
                    yield CompilerNotice(
                        'Error', f"Parameter mismatch, expected `{lhs_param.name}`, got `{rhs_param_type.name}`.",
                        rhs_param.location)

            _mark_checked_recursive(element.rhs)
        case Operator(oper=Token(type=TokenType.Equals)):
            yield from _check(element.lhs)
            yield from _check(element.rhs)
            try:
                lhs_type_decl, lhs_member_decl = resolve_owning_type(element.lhs)
                rhs_type = resolve_type(element.rhs)
            except CompilerNotice as ex:
                yield ex
                return
            if lhs_member_decl.type.const:
                yield CompilerNotice('Error', f"Cannot assign to a const variable.", element.location)
            if isinstance(rhs_type, StaticScope):
                yield CompilerNotice('Error', f"Cannot assign a Scope to a `{lhs_member_decl.type.name}`.",
                                     element.location)
                return
            if isinstance(rhs_type, StaticVariableDecl):
                rhs_decl = rhs_type
                rhs_type = rhs_type.type
            try:
                _check_conversion(rhs_type, lhs_member_decl.type, element.location)
            except CompilerNotice as ex:
                yield ex
                return
        case Namespace():
            with ExitStack() as ex:
                for name in element.name:
                    ex.enter_context(StaticScope.enter(name, location=element.location))
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
        case _:
            yield CompilerNotice('Note', f"Checks for `{type(element).__name__}` are not implemented!",
                                 element.location)
