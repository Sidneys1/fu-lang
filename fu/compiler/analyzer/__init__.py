from typing import Iterable, Iterator, Callable, Generator
from contextlib import ExitStack
from logging import getLogger
from dataclasses import replace

from .. import CompilerNotice
from ..lexer import *
from ..typing import BUILTINS, VOID_TYPE, TypeBase, IntType, FloatType, EnumType, BOOL_TYPE, STR_TYPE, SIZE_TYPE, USIZE_TYPE, ThisType
from ..typing.integral_types import IntegralType
from ..typing.composed_types import ComposedType
from ..typing.composed_types.generic_types import GenericType
from ..typing.composed_types.generic_types.type_ import TypeType
from ..util import set_contextvar

from .static_type import type_from_lex
from .static_scope import StaticScope, _PARSING_BUILTINS, GLOBAL_SCOPE
from .static_variable_decl import StaticVariableDecl, OverloadedMethodDecl

_LOG = getLogger(__package__)

ALL_ELEMENTS: list[Lex] = []
CHECKED_ELEMENTS: list[Lex] = []

# COUNT_CALLS = {}

# def count_calls(func):
#     # global COUNT_CALLS
#     if func not in COUNT_CALLS:
#         COUNT_CALLS[func] = 0
#     from functools import wraps

#     @wraps(func)
#     def _(*args, **kwargs):
#         COUNT_CALLS[func] += 1
#         return func(*args, **kwargs)

#     return _


def _mark_checked_recursive(elem: Lex):
    to_add = [elem]
    while to_add:
        cur = to_add.pop()
        CHECKED_ELEMENTS.append(cur)
        to_add.extend(cur._s_expr()[1])


def check_program(program: Iterable[Document]):
    """Check a whole program."""
    builtins = program[0]
    with set_contextvar(_PARSING_BUILTINS, True):
        # Populate builtins with the special _PARSING_BUILTINS rule.
        yield from _populate(builtins)

    for document in program[1:]:
        # Populate static space.
        yield from _populate(document)

    _LOG.debug(f'Population of static space complete: {GLOBAL_SCOPE.members.keys()}')

    element_count = 0
    for document in program:
        to_add = [document]
        while to_add:
            cur = to_add.pop()
            element_count += 1
            to_add.extend(cur._s_expr()[1])

    _LOG.debug(f"All elements: {len(ALL_ELEMENTS):,}")

    new_program: list[Document] = []
    for document in program:
        new_doc = yield from _optimize(document)
        new_program.append(new_doc)
    program = new_program

    # print('```\n' + str(new_program[-1]) + '```')

    for document in program:
        to_add = [document]
        while to_add:
            cur = to_add.pop()
            ALL_ELEMENTS.append(cur)
            to_add.extend(cur._s_expr()[1])

    # _LOG.debug(f"All elements (after): {element_count:,} (vs {len(ALL_ELEMENTS):,} before)")
    # input()
    yield CompilerNotice('Debug', f"All elements (after): {len(ALL_ELEMENTS):,} (vs {element_count:,} before)", None)

    for document in program:
        yield from _check(document)

    _LOG.debug(f"Checked elements: {len(CHECKED_ELEMENTS):,}")

    unchecked_elements = [x for x in ALL_ELEMENTS if x not in CHECKED_ELEMENTS]
    for elem in unchecked_elements:
        if any(elem in x._s_expr()[1] for x in unchecked_elements):
            continue
        yield CompilerNotice('Info',
                             f"Element `{type(elem).__name__}` was unchecked by static analysis.",
                             location=elem.location)


# @count_calls
def _create_new_type(decl: TypeDeclaration, outer_scope: StaticScope) -> Iterator[CompilerNotice]:
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
                        ret_type = _resolve_type(element.identity.rhs.ident).type
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


# @count_calls
def _populate(element: Lex) -> Iterator[CompilerNotice]:

    # _LOG.debug(f"Populating static identifiers from {type(element).__name__} into {ScopeContext.current().fqdn}")
    match element:
        case Namespace():
            scope = StaticScope.current()
            with ExitStack() as ex:
                for name in element.name:
                    if name in scope.members and not isinstance(scope.members[name], StaticScope):
                        extra = []
                        if isinstance(scope.members[name], StaticVariableDecl):
                            extra.append(CompilerNotice("Note", f"From here.", scope.members[name].location))
                        raise CompilerNotice("Error",
                                             f"{name!r} already exists in {scope.fqdn}!",
                                             element.location,
                                             extra=extra)
                    new_scope = ex.enter_context(StaticScope.enter(name, location=element.location))
                    scope.members[name.value] = new_scope
                    scope = new_scope
                for decl in element.static_scope:
                    yield from _populate(decl)
        case TypeDeclaration(type='type'):
            scope = StaticScope.current()
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
                yield from _create_new_type(element, scope)
        case Declaration(identity=Identity()):
            scope = StaticScope.current()
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
                print(f'\n\n\nxxxx\n\n{element}')
                var_type = type_from_lex(element.identity.rhs, scope)

            if element.initial is not None and not isinstance(element.initial, (Scope, ExpList)):
                rhs_type = _resolve_type(element.initial)
                if isinstance(var_type, TypeType) and rhs_type == var_type.underlying:
                    var_type = var_type.underlying
                elif var_type != rhs_type:
                    yield CompilerNotice('Error',
                                         f"`{element.identity}` is being initialized with a `{rhs_type.name}`.",
                                         element.location)
                    return
            # Add to current scope

            _LOG.debug(f"Adding {name} to {scope.fqdn} as {var_type.name}")
            scope.members[name] = StaticVariableDecl(var_type, element)
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
        case _:
            yield CompilerNotice('Error', f"Static population for `{type(element).__name__}` is not implemented!",
                                 element.location)
    if False:
        yield


# def _resolve_type_for_add(lhs_type, rhs)


# @count_calls
def _resolve_literal_operation(
        element: Operator,
        want: TypeBase | None = None,
        want_signed: bool = False,
        warn: Callable[[CompilerNotice], None] | None = None) -> StaticVariableDecl | TypeBase | StaticScope:
    assert isinstance(element.lhs, Literal) and isinstance(element.rhs, Literal)

    if element.lhs.type != TokenType.Number or element.rhs.type != TokenType.Number:
        raise NotImplementedError()

    lhs_value = element.lhs.to_value()
    rhs_value = element.rhs.to_value()
    assert isinstance(lhs_value, (int, float)) and isinstance(rhs_value, (int, float))

    match element.oper.value:
        case '+':
            val = lhs_value + rhs_value
        case '-':
            val = lhs_value - rhs_value
        case '*':
            val = lhs_value * rhs_value
        case '/':
            val = lhs_value / rhs_value
        case _:
            raise NotImplementedError()

    if isinstance(val, int):
        if isinstance(want, IntType) and want.could_hold_value(val):
            return want
        return IntType.best_for_value(val, want_signed=want_signed)
    if isinstance(val, float):
        if isinstance(want, FloatType) and want.could_hold_value(val):
            return want
        return FloatType.best_for_value(val)


# @count_calls
def _resolve_type(element: Lex,
                  want: TypeBase | None = None,
                  want_signed: bool = False,
                  warn: Callable[[CompilerNotice], None] | None = None) -> StaticVariableDecl | TypeBase | StaticScope:
    if warn is None:

        def x(_: CompilerNotice) -> None:
            pass

        warn = x

    scope = StaticScope.current()

    _LOG.debug(f"Resolving type of {element!r} in {scope.fqdn}")
    match element:
        case ReturnStatement():
            if element.value is None:
                return VOID_TYPE
            return _resolve_type(element.value)
        case Operator(oper=Token(type=TokenType.Dot), lhs=None):
            # prefix dot
            lhs_type = scope.in_scope('this')
            if lhs_type is None:
                raise CompilerNotice(
                    'Error', f"Cannot use `.xyz` syntax, as it is equivalent to `this.xyz` and `this` is not in scope.",
                    element.location)
            lhs_decl = None
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            assert isinstance(element.rhs, Identifier)
            # input(f"OP DOT against lhs members: \n\n{lhs_decl}")
            ret = lhs_type.members.get(element.rhs.value, None)
            if ret is None:
                raise CompilerNotice('Error',
                                     f"{lhs_type.type.name} has no member {element.rhs.value}.",
                                     location=element.location)
            return ret
        case Operator(oper=Token(type=TokenType.Dot)):
            lhs_type = _resolve_type(element.lhs)
            lhs_decl = None
            if isinstance(lhs_type, StaticVariableDecl):
                lhs_decl = lhs_type
                lhs_type = lhs_type.type
            assert isinstance(element.rhs, Identifier)
            ret = lhs_type.members.get(element.rhs.value, None)
            if ret is None:
                raise CompilerNotice('Error',
                                     f"{lhs_type.name} has no member {element.rhs.value}.",
                                     location=element.location)
            return ret
        case Operator(oper=Token(type=TokenType.LBracket)):
            lhs_type = _resolve_type(element.lhs)
            if not lhs_type.indexable:
                raise CompilerNotice('Error', f"{lhs_type.name} is not array indexable.", location=element.lhs.location)
            return lhs_type.indexable[1]
        case Operator(oper=Token(type=TokenType.LParen)):
            lhs_type = _resolve_type(element.lhs).type
            if isinstance(lhs_type, OverloadedMethodDecl):
                if element.rhs is None:
                    rhs_params = tuple()
                else:
                    assert isinstance(element.rhs, ExpList)
                    rhs_params = tuple(_resolve_type(v) for v in element.rhs.values)
                return lhs_type.match(rhs_params).type.return_type
            if lhs_type.callable:
                return lhs_type.callable[1]
            raise CompilerNotice('Error', f"{lhs_type.name} is not callable.", location=element.lhs.location)
        case Operator(oper=Token(type=TokenType.Operator), lhs=None):  # prefix operator
            assert isinstance(element, Operator)
            if element.oper.value == '-' and isinstance(element.rhs, Literal) and element.rhs.type == TokenType.Number:
                raise RuntimeError("This shoudl never happen...")
                return _resolve_type(element.rhs, want=want, want_signed=True)

            rhs_type = _resolve_type(element.rhs)
            if isinstance(rhs_type, StaticVariableDecl):
                rhs_decl = rhs_type
                rhs_type = rhs_type.type
            match element.oper.value, rhs_type:
            # case '-', Literal(type=TokenType.Number):
            #     ...
                case _:
                    raise NotImplementedError(
                        f"Don't know how to resolve type of prefix operator `{element.oper.value}` on `{type(rhs_type).__name__}`"
                    )
        case Operator(oper=Token(type=TokenType.Operator)):
            if element.lhs is None or element.rhs is None:
                raise NotImplementedError(f"Oops! {element.lhs is None} {element.rhs is None}")

            if isinstance(element.lhs, Literal) and isinstance(element.rhs, Literal):
                return _resolve_literal_operation(element, want=want, want_signed=want_signed, warn=warn)

            lhs_type = _resolve_type(element.lhs)
            rhs_type = _resolve_type(element.rhs)
            if isinstance(lhs_type, StaticScope) or isinstance(rhs_type, StaticScope):
                raise CompilerNotice('Error', "Cannot operate on scopes!", element.location)

            # lhs_decl: StaticVariableDecl | None = None
            if isinstance(lhs_type, StaticVariableDecl):
                # lhs_decl = lhs_type
                lhs_type = lhs_type.type
            # rhs_decl: StaticVariableDecl | None = None
            if isinstance(rhs_type, StaticVariableDecl):
                # rhs_decl = rhs_type
                rhs_type = rhs_type.type

            input(f"\n\n{lhs_type.name} {element.oper.value} {rhs_type.name}")
            match lhs_type, rhs_type:
                case IntType(), IntType():
                    assert isinstance(lhs_type, IntType) and isinstance(rhs_type, IntType)
                    oper_name = {
                        '+': 'addition',
                        '-': 'subtraction',
                        '*': 'multiplication',
                        '/': 'division',
                        '!': 'inversion'
                    }.get(element.oper.value, element.oper.value)
                    if lhs_type.signed != rhs_type.signed or lhs_type.size != rhs_type.size:
                        warn(
                            CompilerNotice(
                                'Warning',
                                f"Performing `{oper_name}` between numeric types of different signedness or size can result in inforation loss.",
                                element.location))
                    return max((x for x in (lhs_type, rhs_type)), key=lambda x: x.size or 0)
                case _, _:
                    raise NotImplementedError()
            raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.Equals)):
            return VOID_TYPE
        case Identifier():
            ret = scope.in_scope(element.value)
            if ret is None:
                raise CompilerNotice('Error',
                                     f"Identifier `{element.value}` is not defined.",
                                     location=element.location)
            if isinstance(ret, StaticScope):
                return ret
            # if isinstance(ret, OverloadedMethodDecl):
            #     return ret
            return ret
        case Operator():
            raise CompilerNotice('Note', f"Type resolution for Operator `{element.oper}` is not implemented!",
                                 element.location)
        case Literal():
            match element.type:
                case TokenType.String:
                    return STR_TYPE
                case TokenType.Number:
                    # TODO: determine actual type of literal
                    if want is not None and isinstance(want, IntegralType) and want.could_hold_value(element.value):
                        return want.as_const()
                    return SIZE_TYPE.as_const() if want_signed or element.value[0] == '-' else USIZE_TYPE.as_const()
                case _:
                    raise NotImplementedError()
        case _:
            raise CompilerNotice('Note', f"Type resolution for `{type(element).__name__}` is not implemented!",
                                 element.location)


"""#"""


# @count_calls
def _decl_of(element: Lex) -> StaticVariableDecl:
    match element:
        case Operator(oper=Token(type=TokenType.Dot), lhs=None):
            this_decl = StaticScope.current().in_scope('this')
            assert isinstance(element.rhs, Identifier)
            return this_decl.member_decls.get(element.rhs.value, None)
        case Identifier():
            return StaticScope.current().in_scope(element.value)
        case _:
            raise CompilerNotice('Critical', f"Decl-of checks for {type(element).__name__} are not implemented!",
                                 element.location)


# @count_calls
def _assigns_to(element: Lex) -> Iterator[StaticVariableDecl]:
    match element:
        case Operator(oper=Token(type=TokenType.Equals)):
            yield _decl_of(element.lhs)
        case Statement():
            yield from _assigns_to(element.value)
        case _:
            raise CompilerNotice('Critical', f"Assigns-to checks for {type(element).__name__} are not implemented!",
                                 element.location)


# @count_calls
def _check_type_declaration(element: TypeDeclaration) -> Iterator[CompilerNotice]:
    assert element.type == 'type'
    scope = StaticScope.current()
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
                unassigned.append(this_decl.member_decls[elem.identity.lhs.value])
        yield from _check(elem)

    if ctor is None:
        if unassigned:
            inner = '`, `'.join(x.lex.identity.lhs.value for x in unassigned)
            yield CompilerNotice(
                'Error', f"Type `{scope.fqdn}` has uninitialized members: `{inner}`. Consider adding a constructor?",
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
            'Error', f"Type `{scope.fqdn}` has uninitialized members: `{inner}`. Consider adding a constructor?",
            element.location)


# @count_calls
def _check_declaration(element: Declaration) -> Iterator[CompilerNotice]:
    scope = StaticScope.current()
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

        params = element.identity.rhs.mods[-1]
        assert isinstance(params, ParamList)
        props = {
            p.lhs.value: StaticVariableDecl(type_from_lex(p.rhs, StaticScope.current()).as_const(), p)
            for p in params.params
        }

        with StaticScope.new(element.identity.lhs.value,
                             vars=props,
                             return_type=StaticVariableDecl(lhs_type.callable[1], element)):
            try:
                yield from _populate(element.initial)
                # TODO type check return
                yield from _check(element.initial)
            except CompilerNotice as ex:
                yield ex


"""#"""


# @count_calls
def _check_implicit_conversion(from_: TypeBase | StaticVariableDecl, to_: TypeBase | StaticVariableDecl,
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
        case (TypeBase(size=None), _) | (_, TypeBase(size=None)):
            raise NotImplementedError(f"Can't compare types with unknown sizes ({from_.name} and/or {to_.name})...")
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


# @count_calls
def _resolve_owning_type(element: Lex) -> tuple[StaticVariableDecl, StaticVariableDecl]:
    _LOG.debug(f"Trying to find owning type of `{element}`.")
    scope = StaticScope.current()
    match element:
        case Operator(oper=Token(type=TokenType.Dot), rhs=Identifier()):
            _LOG.debug(f"Trying to find `{element.rhs}` in `{element.lhs}`.")
            lhs_decl = scope.in_scope('this') if element.lhs is None else _resolve_type(element.lhs)
            assert lhs_decl is not None and isinstance(lhs_decl, StaticVariableDecl)
            # print(f"\n\n{scope.members.keys()}\n")
            # input(f"lhs_type is {lhs_decl.type.name}: {lhs_decl.member_decls}")

            member_name = element.rhs.value
            if member_name not in lhs_decl.type.members and member_name not in lhs_decl.member_decls:
                raise CompilerNotice('Error', f"`{lhs_decl.type.name}` does not have a {member_name!r} member.",
                                     element.rhs.location)

            return lhs_decl, lhs_decl.member_decls[member_name]
        case Identifier():
            return None, scope.in_scope(element.value)
        case Operator():
            raise NotImplementedError(f"Don't know how to find owning type of Operator(oper={element.oper.type.name}).")
        case _:
            raise NotImplementedError(f"Don't know how to find owning type of {type(element).__name__}.")


# @count_calls
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


from traceback import format_stack


def _optimize(element: Lex) -> Generator[CompilerNotice, None, Lex]:
    match element:
        case Operator(lhs=None):
            yield CompilerNotice('Info',
                                 f"{type(element.lhs).__name__} {element.oper.value} {type(element.rhs).__name__}",
                                 element.location)
            return element
        case Operator(rhs=None):
            yield CompilerNotice('Info',
                                 f"{type(element.lhs).__name__} {element.oper.value} {type(element.rhs).__name__}",
                                 element.location)
            return element
        case Operator(oper=Token(type=TokenType.Operator)):
            """Infix operator"""
            assert element.rhs is not None and element.lhs is not None

            lhs = yield from _optimize(element.lhs)
            rhs = yield from _optimize(element.rhs)
            match lhs, element.oper.value, rhs:
                case Literal(type=TokenType.Number), '+', Literal(type=TokenType.Number):
                    ret = Literal(value=str(lhs.to_value() + rhs.to_value()),
                                  type=TokenType.Number,
                                  location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized addition of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case Literal(type=TokenType.Number), '-', Literal(type=TokenType.Number):
                    ret = Literal(value=str(lhs.to_value() - rhs.to_value()),
                                  type=TokenType.Number,
                                  location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized subtraction of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case Literal(type=TokenType.Number), '*', Literal(type=TokenType.Number):
                    ret = Literal(value=str(lhs.to_value() * rhs.to_value()),
                                  type=TokenType.Number,
                                  location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized multiplication of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case Literal(type=TokenType.Number), '/', Literal(type=TokenType.Number):
                    ret = Literal(value=str(lhs.to_value() / rhs.to_value()),
                                  type=TokenType.Number,
                                  location=element.location)
                    yield CompilerNotice('Debug',
                                         f"Optimized division of two literals into a new literal ({ret}).",
                                         location=element.location)
                    return ret
                case Literal(), _, Literal():
                    yield CompilerNotice(
                        'Info',
                        f"Not sure how to optimize an infix operator between two literals: {element.lhs}{element.oper.value}{element.rhs}",
                        element.location)
                    # yield CompilerNotice('Info', f"oooh", element.location)
            if lhs != element.lhs or rhs != element.rhs:
                return replace(element, lhs=lhs, rhs=rhs)
            return element
        case Atom() | Statement():
            new_value = yield from _optimize(element.value)
            if new_value != element.value:
                return replace(element, value=new_value)
        case ExpList():
            if not element.values:
                return element
            different = False
            new_values = []
            for e in element.values:
                new_e = yield from _optimize(e)
                if new_e != e:
                    different = True
                    new_values.append(new_e)
                else:
                    new_values.append(e)
            if different:
                return replace(element, values=new_values)
        case ReturnStatement():
            if element.value is None:
                return element
            new_value = yield from _optimize(element.value)
            if new_value != element.value:
                return replace(element, value=new_value)
        case Scope():
            if not element.content:
                return element
            different = False
            new_content = []
            for e in element.content:
                new_e = yield from _optimize(e)
                if new_e != e:
                    different = True
                    new_content.append(new_e)
                else:
                    new_content.append(e)
            if different:
                return replace(element, content=new_content)
        case Declaration():
            if element.initial is None:
                return element
            initial = yield from _optimize(element.initial)
            if initial != element.initial:
                return replace(element, initial=initial)
        case TypeDeclaration():
            if element.definition is None:
                return element
            if isinstance(element.definition, Type_):
                return element
            different = False
            new_defs = []
            for e in element.definition:
                new_e = yield from _optimize(e)
                if new_e != e:
                    different = True
                    new_defs.append(new_e)
                else:
                    new_defs.append(e)
            if different:
                return replace(element, definition=new_defs)
        case Document():
            different = False
            content: list[Declaration | TypeDeclaration | Namespace] = []
            for c in element.content:
                new_c = yield from _optimize(c)
                if new_c is not None and new_c != c:
                    different = True
                    content.append(new_c)
                else:
                    content.append(c)
            if different:
                return replace(element, content=content)
        case Literal() | Operator(oper=Token(type=TokenType.Dot)) | Operator(oper=Token(type=TokenType.Equals)):
            """Ignore"""
        case _:
            yield CompilerNotice('Note', f"Don't know how to optimize `{type(element).__name__}`.", element.location)
    return element


# @count_calls
def _check(element: Lex) -> Iterator[CompilerNotice]:
    scope = StaticScope.current()
    _LOG.debug(f"Checking {type(element).__name__} in {scope.fqdn}")
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
                vars = {'this': scope.members[element.name.value]}
                if element.generic_params is not None:
                    for x in element.generic_params.params or ():
                        vars[x.value] = StaticVariableDecl(GenericType.GenericParam(x.value), x)

                with StaticScope.new(element.name.value, vars):
                    yield from _check_type_declaration(element)
            except CompilerNotice as ex:
                yield ex
            # except Exception as ex:
            #     yield CompilerNotice('Critical', f"Unknown error when checking {element!r}: {ex}", element.location)
        case ReturnStatement():
            if element.value is not None:
                yield from _check(element.value)
            try:
                returned_type = _resolve_type(element)
                assert not isinstance(returned_type, StaticScope)
                try:
                    _check_implicit_conversion(returned_type, scope.return_type.type, element.location)
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
            lhs_type = _resolve_type(element.lhs)
            if not lhs_type.indexable:
                yield CompilerNotice('Error', f"`{lhs_type.name}` is not array indexable.", location=element.location)
                return
            rhs_type = _resolve_type(element.rhs)
            lhs_expected = lhs_type.indexable[0]
            try:
                _check_implicit_conversion
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
            lhs_type = _resolve_type(element.lhs)
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
            eval_type = _resolve_type(element.value, warn=lambda x: warns.append(x))
            yield from warns
            if eval_type != VOID_TYPE:
                yield CompilerNotice('Warning', f"`{eval_type.name}` result of statement is discarded?",
                                     element.location)
            # input(f"\n\n`{str(element).strip()}` evals to `{eval_type.name}`")
        case ExpList():
            for x in element.values:
                if isinstance(x, Literal):
                    _mark_checked_recursive(x)
                else:
                    yield from _check(x)
        case Operator(oper=Token(type=TokenType.LParen)):
            yield from _check(element.lhs)
            if element.rhs is not None:
                yield from _check(element.rhs)

            try:
                type_of_lhs = _resolve_type(element.lhs)
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
                rhs_param_type = _resolve_type(rhs_param, want=lhs_param)
                if lhs_param != rhs_param_type:
                    yield CompilerNotice(
                        'Error', f"Parameter mismatch, expected `{lhs_param.name}`, got `{rhs_param_type.name}`.",
                        rhs_param.location)

            _mark_checked_recursive(element.rhs)
        case Operator(oper=Token(type=TokenType.Equals)):
            yield from _check(element.lhs)
            yield from _check(element.rhs)
            try:
                lhs_type_decl, lhs_member_decl = _resolve_owning_type(element.lhs)
                rhs_type = _resolve_type(element.rhs)
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
            _check_implicit_conversion(rhs_type, lhs_member_decl.type, element.location)
            # if rhs_type != lhs_member_decl.type:
            #     yield CompilerNotice(
            #         'Error',
            #         f"Cannot assign a value of type `{rhs_type.name}` to a variable of type `{lhs_member_decl.type.name}`.",
            #         element.location)
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
                yield from _check(content)
        case Operator():
            yield CompilerNotice(
                'Note',
                f"Checks for `Operator(oper={element.oper},lhs={element.lhs},rhs={element.rhs})` are not implemented!",
                element.location)
        case Atom():
            yield from _check(element.value)
        case Literal():
            pass
        case _:
            yield CompilerNotice('Note', f"Checks for `{type(element).__name__}` are not implemented!",
                                 element.location)


"""#"""
