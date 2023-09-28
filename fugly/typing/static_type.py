from typing import Self, TYPE_CHECKING
from dataclasses import dataclass, field

from . import _LOG as _MODULE_LOG
from .. import SourceLocation, CompilerNotice
from ..lexer import Type_, ParamList, ArrayDef

_LOG = _MODULE_LOG.getChild(__name__)

if TYPE_CHECKING:
    from ..analyzer import ScopeContext

_EXISTING_TYPES: set['StaticType'] = set()


@dataclass(frozen=True, slots=True, kw_only=True)
class StaticType:
    """Describes a Type that was resolvable at static analysis time."""

    name: str = field(kw_only=False)
    defined_at: SourceLocation | None = field(repr=False, compare=False, default=None)
    evals_to: Self | None = None
    members: dict[str, Self] = field(default_factory=dict)
    callable: tuple[Self, ...] | None = None
    array: bool | int = False

    @classmethod
    def from_type(cls, type: Type_, scope: 'ScopeContext') -> Self:
        lhs_type = scope.in_scope(type.ident.value)
        if lhs_type is None:
            raise CompilerNotice('Error', f"`{type.ident.value}` is undefined.", type.ident.location)
        if not type.mods:
            return lhs_type
        return cls._from_type_recursive(lhs_type, list(type.mods), scope)

    @classmethod
    def _from_type_recursive(cls, type: Self, mods: list[ParamList | ArrayDef], scope: 'ScopeContext') -> Self:
        evals_to: Self | None = type
        while mods:
            mod = mods.pop(0)
            match mod:
                case ArrayDef():
                    add = "[]" if mod.size is None else f"[{mod.size.value}]"
                    evals_to = cls(evals_to.name + add, array=True if mod.size is None else int(mod.size.value))
                case ParamList():
                    callable = tuple(cls.from_type(x.rhs, scope) for x in mod.params if x.rhs != 'namespace')
                    add = '(' + ', '.join(x.name for x in callable) + ')'
                    evals_to = cls(evals_to.name + add, callable=callable)
                case _:
                    raise NotImplementedError()
            # Resolve known types...
            evals_to = next((x for x in _EXISTING_TYPES if x == evals_to), evals_to)
        return evals_to
