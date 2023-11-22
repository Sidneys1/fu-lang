from dataclasses import dataclass

from ...virtual_machine.bytecode.structures import SourceLocation


@dataclass(slots=True)
class TempSourceMap:
    offset: int
    length: int
    location: SourceLocation
