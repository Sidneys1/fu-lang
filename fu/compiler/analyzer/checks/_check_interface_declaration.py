from typing import Iterator

from ....types import InterfaceType, ThisType, StaticType
from ... import CompilerNotice
from ...lexer import CompilerNotice, Declaration, Identity, Type_, TypeDeclaration
from .. import _mark_checked_recursive
from ..scope import AnalyzerScope
from ..static_variable_decl import decl_of
from ._check_type_alias import _check_type_alias


def _check_interface_declaration(element: TypeDeclaration) -> Iterator[CompilerNotice]:
    assert element.type == 'interface'
    scope = AnalyzerScope.current()

    _mark_checked_recursive(element.name)
    assert element.definition is not None and not isinstance(element.definition, Type_)

    this_decl = scope.members['this']
    assert isinstance(this_decl.type, ThisType)
    actual_type = this_decl.type.resolved
    if actual_type is None:
        raise CompilerNotice('Critical', f"Got unresolved `this`!", element.location)
    # this_decl = scope.members['this']
    for elem in element.definition:
        match elem:
            case TypeDeclaration(definition=None):
                yield CompilerNotice('Error', "Forward-declaration of types is not allowed.", elem.location)
            case TypeDeclaration(definition=Type_()):
                # Type alias.
                yield from _check_type_alias(elem)
            case Declaration(identity=Identity()) if elem.initial is None and elem.identity.lhs.value == 'this':
                # Special case - inheritance
                inherits_decl = decl_of(elem.identity.rhs)
                assert isinstance(inherits_decl.type, StaticType)
                inherits_type = inherits_decl.type.underlying
                if not isinstance(inherits_type, InterfaceType):
                    # Interface is inheriting something other than an interface.
                    # TODO: just assert that we haven't inherited twice?
                    pass
                else:
                    # We've inherited an interface.
                    # We just become an amalgamation of both interfaces.
                    # No specific checks.
                    # TODO: make sure we haven't inherited twice?
                    pass
                _mark_checked_recursive(elem)
                continue
                # # print(f"Checking {actual_type.name} against inherited interface {inherits_type.name}")
                # extra: list[CompilerNotice] = []
                # for k, v in inherits_decl.member_decls.items():
                #     assert isinstance(v, StaticVariableDecl)
                #     actual = actual_type.members.get(k, None)
                #     if actual is None:
                #         extra.append(CompilerNotice('Error', f"Missing `{k}`, defined here.", v.location))
                #         continue
                #     actual_decl = this_decl.member_decls[k]
                #     # print(f"\t{k} must be {v.name} (it's {actual.name!r}, or {v == actual=})")
                #     if v.type == actual:
                #         extra.append(
                #             CompilerNotice('Error', f"Expected `{k}` to be `{v.type.name}`, got `{actual.name}`.",
                #                         actual_decl.location))
                #         extra.append(CompilerNotice('Note', f"As specified here:", v.location))
                # # input(f"\tOverall: {not extra}")
                # if extra:
                #     yield CompilerNotice('Error', f"Type does not fully implement interface `{inherits_type.name}`:",
                #                         elem.location, extra)
            case Declaration():
                # if elem.initial is not None:
                #     yield CompilerNotice('Error', "Interface members cannot have implementations.", elem.location)
                _mark_checked_recursive(elem)
            case _:
                yield CompilerNotice('Critical',
                                     f"Interface definition checks for `{type(elem).__name__}` are not implemented.",
                                     elem.location)
