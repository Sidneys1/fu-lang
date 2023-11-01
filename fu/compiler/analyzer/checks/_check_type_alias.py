from typing import Iterator

from ....types import ThisType
from ... import CompilerNotice
from ...lexer import CompilerNotice, Type_, TypeDeclaration
from .. import _mark_checked_recursive
from ..scope import AnalyzerScope


def _check_type_alias(element: TypeDeclaration) -> Iterator[CompilerNotice]:
    # An alias
    assert isinstance(element.definition, Type_)

    scope = AnalyzerScope.current()
    name = element.name.value
    if scope.parent is not None and (outer_decl := scope.parent.in_scope(name)) is not None:
        yield CompilerNotice('Warning',
                             f"Declaration of {name!r} shadows previous declaration.",
                             location=element.location,
                             extra=[CompilerNotice('Note', "Here.", location=outer_decl.location)])
    # Check redefinition
    if (inner_decl := scope.members.get(name, None)) is not None:
        # TODO: overloaded methods
        # if isinstance(inner_decl, OverloadedMethodDecl):
        #     ...
        # el
        if inner_decl.location is not element.name.location and not (isinstance(inner_decl.type, ThisType)
                                                                     and scope.type == AnalyzerScope.Type.Type):
            yield CompilerNotice('Error',
                                 f"Redefinition of {name!r}.",
                                 location=element.location,
                                 extra=[CompilerNotice('Note', "Here.", location=inner_decl.location)])
    _mark_checked_recursive(element)
