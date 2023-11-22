from enum import Enum
from dataclasses import dataclass

from ...types import TypeBase

from ..analyzer.static_variable_decl import StaticVariableDecl

from .scope import AnalyzerScope


class Storage(Enum):
    Arguments = 'args'
    Locals = 'locals'
    Heap = 'heap'
    Stack = 'stack'
    Static = 'static'


@dataclass(slots=True)
class StorageDescriptor:
    storage: Storage
    type: TypeBase | AnalyzerScope
    decl: StaticVariableDecl | None = None
    slot: int | None = None

    def __post_init__(self) -> None:
        assert isinstance(self.type, (TypeBase, AnalyzerScope))
