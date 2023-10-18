import sys
from pathlib import Path
from logging import basicConfig, DEBUG

from pytest import fixture

ROOT = Path(__file__).parent.parent.absolute()
SRC = ROOT

assert SRC.is_dir()
assert (SRC / 'fu').is_dir()
assert (SRC / 'fu' / '__init__.py').is_file()

sys.path.insert(0, str(SRC))

basicConfig(level=DEBUG)
