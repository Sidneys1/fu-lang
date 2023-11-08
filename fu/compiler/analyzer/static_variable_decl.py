from dataclasses import dataclass, field, replace
from typing import Self

# from .static_type import StaticType
from ...types import TypeBase
from .. import CompilerNotice, SourceLocation
from ..lexer import Declaration, Identifier, Identity, Lex, Operator, Type_, TypeDeclaration
from ..tokenizer import Token, TokenType


@dataclass(frozen=True, slots=True)
class StaticVariableDecl:
    """Describes the declaration of a variable during static analysis."""
    type: TypeBase
    lex: Declaration | Identity | TypeDeclaration
    fqdn: str | None = field(default=None, kw_only=True)
    parent: Self | None = field(default=None, kw_only=True)
    member_decls: dict[str, 'StaticVariableDecl'] = field(default_factory=dict, kw_only=True)

    def __post_init__(self):
        assert isinstance(self.type, TypeBase)

    @property
    def location(self) -> SourceLocation:
        if isinstance(self.lex, TypeDeclaration):
            return self.lex.name.location
        if isinstance(self.lex, Declaration):
            return self.lex.identity.location
        return self.lex.location

    @property
    def name(self) -> str:
        if isinstance(self.lex, TypeDeclaration):
            return f"{self.lex.name.value}: {self.lex.type}"
        if isinstance(self.lex, Identity):
            return f"{self.lex.lhs.value}: {self.type.name}"
        if isinstance(self.lex, Identifier):
            return f"{self.lex.value}: {self.type.name}"
        assert isinstance(self.lex, Declaration), f"Expected Declaration, got `{type(self.lex).__name__}`"
        return f"{self.lex.identity.lhs}: {self.type.name}"

    def as_const(self) -> Self:
        return replace(self, type=replace(self.type, const=True))


@dataclass(frozen=True, slots=True)
class OverloadedMethodDecl(StaticVariableDecl):
    """Describes the declarations of an overloaded method during static analysis."""
    overloads: list[StaticVariableDecl]

    # def match(self, params: tuple[TypeBase, ...]) -> StaticVariableDecl:
    #     # input(
    #     #     f"Searching for \n({','.join(x.name for x in params)})\n in \n[{', '.join(repr(o.type.params) for o in self.overloads)}]"
    #     # )
    #     for overload in self.overloads:
    #         # assert isinstance(overload.type, CallableType)
    #         if overload.type.params == params:
    #             # input(f"{overload.type.params == params=}")
    #             return overload


def decl_of(element: Lex) -> StaticVariableDecl:
    from .scope import AnalyzerScope
    match element:
        case Type_():
            scope = AnalyzerScope.current()
            base_decl = scope.in_scope(element.ident.value)
            assert isinstance(
                base_decl, StaticVariableDecl), f"`{element.ident.value}` in {scope.fqdn} a {type(base_decl).__name__}"
            return base_decl
        case Operator(oper=Token(type=TokenType.Dot), lhs=None):
            this_decl = AnalyzerScope.current().in_scope('this')
            assert isinstance(element.rhs, Identifier)
            return this_decl.member_decls.get(element.rhs.value, None)
        case Identifier():
            return AnalyzerScope.current().in_scope(element.value)
        case _:
            raise CompilerNotice('Critical', f"Decl-of checks for {type(element).__name__} are not implemented!",
                                 element.location)
