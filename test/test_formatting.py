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

FAKE_FILES = (
    FAKE_EMPTY_FILE,
    FAKE_NEWLINE_FILE,
    FAKE_WHITESPACE_FILE,
    FAKE_LINE_COMMENT_FILE,
    FAKE_BLOCK_COMMENT_FILE,
    FAKE_NAMESPACE,
    FAKE_NAMESPACE_COMMENTS,
)


class FakeFile(AbstractContextManager[StringIO]):
    """Represents a fake file based on StringIO contents."""

    def __init__(self, fake_path: str, contents: str) -> None:
        self._fake_path = fake_path
        self._contents = contents
        self._io: StringIO | None = None
        self._tok: Optional['CtxToken'] = None

    def __enter__(self) -> Any:
        from fu.compiler import SourceFile
        assert self._tok is None and self._io is None
        self._tok = SourceFile.set(self._fake_path)
        self._io = StringIO(self._contents)
        return self._io

    def __exit__(self, *_) -> bool | None:
        from fu.compiler import SourceFile
        assert self._tok is not None and self._io is not None
        SourceFile.reset(self._tok)
        self._tok = None
        self._io = None
        return None


def _test_formatting(input_: str, output: str):
    diffs = '\n\t'.join(
        f"Line {i}: {line[0:2]}{line[2:]!r}"
        for i, line in enumerate(Differ().compare(input_.splitlines(keepends=True), output.splitlines(keepends=True)))
        if line[0:2] in ('- ', '+ '))
    if diffs:
        assert False, "Input and output differ:\n\t" + diffs


@mark.parametrize('content', FAKE_FILES)
def test_formatting_fake(content):
    from fu.compiler import ImmutableTokenStream
    from fu.compiler.stream import TokenStream, StrStream
    from fu.compiler.tokenizer import Token
    from fu.compiler.lexer import parse

    with FakeFile('empty.py', content) as file:
        stream = TokenStream([], generator=Token.token_generator(StrStream(file)))
        document = parse(cast(ImmutableTokenStream, stream))

    assert document is not None, "Failed to parse."

    _test_formatting(content, str(document))


def test_formatting_builtins():
    from fu.compiler.discovery import parse_file, DEFAULT_STD_ROOT

    document = parse_file(DEFAULT_STD_ROOT / '__builtins__.fu')

    assert document is not None

    with (DEFAULT_STD_ROOT / '__builtins__.fu').open() as file:
        full_text = file.read()

    _test_formatting(full_text, str(document))
