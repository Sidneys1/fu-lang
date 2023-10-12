from dataclasses import dataclass, field, replace
from typing import Self

from .. import SourceLocation

# from .static_type import StaticType
from ..typing import TypeBase
from ..lexer.declaration import Declaration, TypeDeclaration


@dataclass(frozen=True, slots=True)
class StaticVariableDecl:
    """Describes the declaration of a variable during static analysis."""
    type: TypeBase
    lex: Declaration | TypeDeclaration
    parent: Self | None = field(default=None, kw_only=True)
    member_decls: dict[str, Self] = field(default_factory=dict, kw_only=True)

    def __post_init__(self):
        assert isinstance(self.type, TypeBase)

    @property
    def location(self) -> SourceLocation:
        if isinstance(self.lex, TypeDeclaration):
            return self.lex.name.location
        return self.lex.identity.location

    @property
    def name(self) -> str:
        return f"{self.lex.identity.lhs}: {self.type.name}"

    def as_const(self) -> Self:
        return replace(self, type=replace(self.type, const=True))


@dataclass(frozen=True, slots=True)
class OverloadedMethodDecl(StaticVariableDecl):
    """Describes the declarations of an overloaded method during static analysis."""
    overloads: list[StaticVariableDecl]

    def match(self, params: tuple[TypeBase, ...]) -> StaticVariableDecl:
        # input(
        #     f"Searching for \n({','.join(x.name for x in params)})\n in \n[{', '.join(repr(o.type.params) for o in self.overloads)}]"
        # )
        for overload in self.overloads:
            # assert isinstance(overload.type, CallableType)
            if overload.type.params == params:
                # input(f"{overload.type.params == params=}")
                return overload
