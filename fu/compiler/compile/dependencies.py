from dataclasses import dataclass, field
from io import BytesIO

from ...virtual_machine.bytecode import _encode_u16, int_u16, int_u32
from ...virtual_machine.bytecode.builder import BytecodeBuilder

from ..analyzer.static_variable_decl import StaticVariableDecl

from .scope import CompileScope
from .util import write_to_buffer


@dataclass(slots=True)
class Dependency:
    on: BytesIO


@dataclass(slots=True)
class DependantFunction(Dependency):
    decl: StaticVariableDecl
    fqdn_id: int_u32 = field(init=False)
    id_: int_u16 = field(init=False)

    def __post_init__(self) -> None:
        fqdn = self.decl.fqdn
        builder = BytecodeBuilder.current()
        assert fqdn is not None and builder is not None
        self.fqdn_id = builder.add_string(fqdn)
        value = builder.function_map.get(self.fqdn_id, None)
        if value is None:
            value = builder.reserve_function(self.fqdn_id)
            CompileScope.current().add_dep(self)
        self.id_ = value

    def id(self) -> bytes:
        return _encode_u16(self.id_)

    def _patch(self, patch_location: int) -> None:
        self.on.seek(patch_location)
        write_to_buffer(self.on, _encode_u16(self.id_))


__all__ = ('Dependency', 'DependantFunction')
