from pathlib import Path
from typing import Iterator, cast

from . import CompilerNotice, ImmutableTokenStream, SourceFile, SourceLocation
from .lexer import Document, parse
from .stream import StrStream, TokenStream
from .tokenizer import Token
from .util import set_contextvar

DEFAULT_STD_ROOT = Path(__file__).parent.parent.parent / 'lib'


def parse_file(path: Path) -> Document:
    """Parse a single file"""
    # input(f"compiling {path!r} relative to {Path.cwd()}")
    with set_contextvar(SourceFile, str(path.relative_to(Path.cwd()))), open(path, 'r', encoding='utf-8') as file:
        stream = TokenStream([], generator=Token.token_generator(StrStream(file)))
        doc = parse(cast(ImmutableTokenStream, stream))
        if doc is None:
            raise CompilerNotice('Error', f"Failed to parse '{path.relative_to(Path.cwd())}'.",
                                 SourceLocation((0, 0), (0, 0), (0, 0)))
        return doc


def load_std(std_root: Path = DEFAULT_STD_ROOT) -> Iterator[Document]:
    """Load the standard library."""
    builtins = std_root / '__builtins__.fu'
    yield parse_file(builtins)
    for path in std_root.glob('**/*.fu'):
        if path.name.startswith('.') or path == builtins:
            continue
        yield parse_file(path)


def discover_files(root: Path) -> Iterator[Document]:
    """Discover files under `root` and parse them."""
    assert root.is_dir()
    for file in root.glob('**/*.fu', case_sensitive=False):
        assert file.is_file()
        yield parse_file(file.absolute())
