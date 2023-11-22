from io import BytesIO
from typing import Iterator

from ...types import BOOL_TYPE
from ...virtual_machine.bytecode import OpcodeEnum

from ..lexer import Expression, IfStatement, ReturnStatement, Scope, Statement

from .label import Label
from .util import write_to_buffer
from ._temp_source_map import TempSourceMap
from ._compile_expression import compile_expression


def _emit_if_body(content: Scope | Statement | ReturnStatement,
                  buffer: BytesIO,
                  *,
                  end_label: Label | None = None) -> Iterator[TempSourceMap]:
    from . import compile_blocks, compile_statement
    if isinstance(content, Scope):
        yield from compile_blocks(content.content, buffer)
    else:
        yield from compile_statement(content, buffer)

    if end_label is not None:
        write_to_buffer(buffer, OpcodeEnum.JMP, end_label)


def _emit_if_head(term: Expression, buffer: BytesIO, next_case: Label) -> Iterator[TempSourceMap]:
    from .convert_to_stack import convert_to_stack
    start = buffer.tell()
    storage = yield from compile_expression(term, buffer, BOOL_TYPE)
    convert_to_stack(storage, BOOL_TYPE, buffer, term.location)
    write_to_buffer(buffer, OpcodeEnum.JZ, next_case)
    yield TempSourceMap(start, buffer.tell() - start, term.location)


def compile_if_statement(statement: IfStatement, buffer: BytesIO) -> Iterator[TempSourceMap]:
    assert statement.term is not None
    next_case_label = Label(buffer)
    yield from _emit_if_head(statement.term, buffer, next_case_label)

    other_cases: list[IfStatement] = list(statement.content[1:])  # type: ignore

    has_else_block = other_cases and isinstance(last := statement.content[-1], IfStatement) and last.term is None
    else_block: IfStatement | None = None
    if has_else_block:
        last_block = other_cases.pop()
        assert isinstance(last_block, IfStatement)
        else_block = last_block

    end_label = Label(buffer)

    # jumps_to_end = []
    assert isinstance(
        statement.content[0],
        (Scope, Statement, ReturnStatement)), f"Body was unexpectedly a `{type(statement.content[0]).__name__}`!"
    yield from _emit_if_body(statement.content[0], buffer, end_label=end_label if bool(other_cases) else None)

    for case in other_cases:
        assert isinstance(case, IfStatement) and case.term is not None
        next_case_label.link()

        # Emit head
        next_case_label = Label(buffer)
        yield from _emit_if_head(case.term, buffer, next_case_label)

        # Emit body
        assert not isinstance(case.content[0], IfStatement)
        yield from _emit_if_body(case.content[0], buffer, end_label=end_label)

    next_case_label.link()

    if else_block is not None:
        # Emit body
        assert len(else_block.content) == 1
        assert not isinstance(else_block.content[0], IfStatement)
        yield from _emit_if_body(else_block.content[0], buffer)

    # Rewrite the jumps to the end...
    end_label.link()
