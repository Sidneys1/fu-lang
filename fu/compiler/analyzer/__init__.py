from typing import Iterable
from logging import getLogger

from .. import CompilerNotice
from ..util import set_contextvar
from ..lexer import *

_LOG = getLogger(__package__)

from ._populate import _populate

ALL_ELEMENTS: list[Lex] = []
CHECKED_ELEMENTS: list[Lex] = []

from .scope import AnalyzerScope, _PARSING_BUILTINS, GLOBAL_SCOPE
from .static_variable_decl import StaticVariableDecl
from .optimization import _optimize
from .resolvers import *


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

    _LOG.debug(f"All elements (after): {len(ALL_ELEMENTS):,} (vs {element_count:,} before)")
    # input()
    # yield CompilerNotice('Debug', f"All elements (after): {len(ALL_ELEMENTS):,} (vs {element_count:,} before)", None)

    from .checks import _check
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
