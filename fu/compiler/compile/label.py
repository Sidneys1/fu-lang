from io import BytesIO
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from fu.virtual_machine.bytecode import _encode_numeric, int_i16


@dataclass(slots=True)
class Label(AbstractContextManager):
    on: BytesIO
    patch_locations: list[int] = field(default_factory=list)
    _location: int | None = field(init=False, default=None)

    def append(self, *patch_locations: int) -> None:
        if self._location is not None:
            pos = self.on.tell()
            for x in self.patch_locations:
                self._patch(x)
            self.on.seek(pos)
            return
        self.patch_locations.extend(patch_locations)

    def relative(self) -> bytes:
        pos = self.on.tell()
        if self._location is not None:
            return _encode_numeric((self._location - pos) - 2, int_i16)
        self.patch_locations.append(pos)
        return b'\xde\xad'

    def _patch(self, patch_location: int) -> None:
        from fu.compiler.compile.util import write_to_buffer
        self.on.seek(patch_location)
        write_to_buffer(self.on, _encode_numeric((self._location - patch_location) - 2, int_i16))

    def link(self) -> None:
        """
        Link this Label to a location.

        Any existing patch_locations will be patched.

        Any future patch locations will be patched immediately.
        """
        if self._location is not None:
            raise ValueError()

        self._location = self.on.tell()
        while self.patch_locations:
            self._patch(self.patch_locations.pop())
        self.on.seek(self._location)

    def __exit__(self, __exc_type: type[BaseException] | None, _, __) -> bool | None:
        if __exc_type is None:
            self.link()
        return None
