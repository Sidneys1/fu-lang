from contextlib import AbstractContextManager
from io import StringIO
from typing import TYPE_CHECKING, Any, Optional, cast
from difflib import Differ

from pytest import mark

if TYPE_CHECKING:
    from contextvars import Token as CtxToken

FAKE_EMPTY_FILE = """"""
FAKE_NEWLINE_FILE = """\n"""
FAKE_WHITESPACE_FILE = """\n\n"""
FAKE_LINE_COMMENT_FILE = """// Comment\n"""
FAKE_BLOCK_COMMENT_FILE = """/* Comment */\n"""
FAKE_MULTILINE_BLOCK_COMMENT_FILE = """\
/*
 * Comment
 */
"""
FAKE_NAMESPACE = """foo: namespace = { };"""

FAKE_NAMESPACE_COMMENTS = """\
// foo namespace
foo: namespace = {
  /* block comments! */
  // line comments!
};
// Another one
"""

FAKE_DECL = """foo: u8 = 0;"""
FAKE_FUNC = """main: void() = { };"""
FAKE_FUNC_COMMENT = """\
main: void() = {
  // Comment!
};"""
FAKE_FUNC_RETURN = """\
main: u8(x: u8) = {
  return x;
};"""
FAKE_FUNC_STATEMENT = """\
main: u8(x: u8, y: u8) = {
  x = (x + 3);
};"""

FAKE_TYPE = """bar: type;"""
FAKE_TYPE_ALIAS = """bar: type = u8;"""
FAKE_TYPE_EMPTY = """bar: type = { };"""
FAKE_TYPE_DEF = """\
bar: type = {
  // Comment!
  this: u8;
};"""
FAKE_TYPE_GENERIC = """\
bar: type<T> = {
  this: T;
};"""

FAKE_OPER_DOT = """x: void = a.b;"""
FAKE_OPER_PAREN = """x: void = a(b);"""
FAKE_OPER_BRACE = """x: void = a[0];"""
FAKE_OPER_PRE = """x: void = -x;"""
FAKE_OPER_NEG = """x: void = -0;"""
FAKE_OPER_PRECENDENCE = """x: void = 1 * (2 + 3);"""

FAKE_FILES = (
    FAKE_EMPTY_FILE,
    FAKE_NEWLINE_FILE,
    FAKE_WHITESPACE_FILE,
    FAKE_LINE_COMMENT_FILE,
    FAKE_BLOCK_COMMENT_FILE,
    FAKE_NAMESPACE,
    FAKE_NAMESPACE_COMMENTS,
    FAKE_DECL,
    FAKE_FUNC,
    FAKE_FUNC_COMMENT,
    FAKE_FUNC_RETURN,
    FAKE_FUNC_STATEMENT,
    FAKE_TYPE,
    FAKE_TYPE_ALIAS,
    FAKE_TYPE_EMPTY,
    FAKE_TYPE_DEF,
    FAKE_TYPE_GENERIC,
    FAKE_OPER_DOT,
    FAKE_OPER_PAREN,
    FAKE_OPER_BRACE,
    FAKE_OPER_PRE,
    FAKE_OPER_NEG,
    FAKE_OPER_PRECENDENCE,
)

from conftest import FakeFile


def _test_formatting(input_: str, output: str):
    assert input_ == output
    diffs = '\n\t'.join(
        f"Line {i}: {line[0:2]}{line[2:]!r}"
        for i, line in enumerate(Differ().compare(input_.splitlines(keepends=True), output.splitlines(keepends=True)))
        if line[0:2] in ('- ', '+ '))
    if diffs:
        assert False, "Input and output differ:\n\t" + diffs


@mark.parametrize('content', FAKE_FILES)
def test_formatting_fake(global_scope, content):
    from fu.compiler import ImmutableTokenStream
    from fu.compiler.stream import TokenStream, StrStream
    from fu.compiler.tokenizer import Token
    from fu.compiler.lexer import parse

    with FakeFile('empty.py', content) as file:
        stream = TokenStream([], generator=Token.token_generator(StrStream(file)))
        document = parse(cast(ImmutableTokenStream, stream))

    assert document is not None, "Failed to parse."

    _test_formatting(content, str(document))


@mark.parametrize('content', FAKE_FILES)
def test_repr_fake(global_scope, content):
    from fu.compiler import ImmutableTokenStream
    from fu.compiler.stream import TokenStream, StrStream
    from fu.compiler.tokenizer import Token
    from fu.compiler.lexer import parse

    with FakeFile('empty.py', content) as file:
        stream = TokenStream([], generator=Token.token_generator(StrStream(file)))
        document = parse(cast(ImmutableTokenStream, stream))

    assert document is not None, "Failed to parse."
    repr(document)


@mark.parametrize('content', FAKE_FILES)
def test_unrepr_fake(global_scope, content):
    from fu.compiler import ImmutableTokenStream
    from fu.compiler.stream import TokenStream, StrStream
    from fu.compiler.tokenizer import Token
    from fu.compiler.lexer import parse

    with FakeFile('empty.py', content) as file:
        stream = TokenStream([], generator=Token.token_generator(StrStream(file)))
        document = parse(cast(ImmutableTokenStream, stream))

    assert document is not None, "Failed to parse."
    document.unrepr()


def test_formatting_builtins(global_scope, ):
    from fu.compiler.discovery import parse_file, DEFAULT_STD_ROOT

    document = parse_file(DEFAULT_STD_ROOT / '__builtins__.fu')

    assert document is not None

    with (DEFAULT_STD_ROOT / '__builtins__.fu').open() as file:
        full_text = file.read()

    _test_formatting(full_text, str(document))
