import sys
from pathlib import Path
from logging import basicConfig, DEBUG, ERROR
from contextlib import AbstractContextManager
from io import StringIO
from typing import Optional, Any
from contextvars import Token as CtxToken

from pytest import fixture

ROOT = Path(__file__).parent.parent.absolute()
SRC = ROOT

assert SRC.is_dir()
assert (SRC / 'fu').is_dir()
assert (SRC / 'fu' / '__init__.py').is_file()

sys.path.insert(0, str(SRC))

def pytest_configure(config):
    basicConfig(level=DEBUG if config.getoption("verbose") > 0 else ERROR)

@fixture
def global_scope():
    from fu.compiler.analyzer.scope import set_global_scope, AnalyzerScope 
    global_scope = AnalyzerScope(None)
    with set_global_scope(global_scope):
        yield global_scope

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
