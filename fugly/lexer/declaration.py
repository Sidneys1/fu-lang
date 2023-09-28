from typing import Union, Self, TYPE_CHECKING

from . import Expression, Identifier, Identity, Lex, LexError, MetadataList, lex_dataclass, _tab, Namespace  #, _new_scope, Type_, ParamList, CompilerNotice
from ..tokenizer import SourceLocation, TokenStream, TokenType

if TYPE_CHECKING:
    from . import Scope


@lex_dataclass
class Declaration(Lex):
    """Declaration: Identity [ '=' Expression | Scope ];"""
    identity: Identity
    initial: Union['Scope', 'Expression', None] = None
    metadata: MetadataList | None = None

    def __str__(self) -> str:
        from . import Scope, Statement
        if self.identity is not None and self.identity.rhs == 'namespace' and isinstance(self.initial, Scope) and len(
                self.initial.content) == 1 and isinstance(self.initial.content[0], Statement) and isinstance(
                    self.initial.content[0].value,
                    Declaration) and self.initial.content[0].value.identity.rhs == 'namespace':
            return f"{self.identity.lhs}.{self.initial.content[0].value}"

        build = ''

        if self.metadata:
            build += f"[{self.metadata}]\n{_tab()}"

        build += str(self.identity)

        if self.initial is not None:
            build += f" = {self.initial}"
        return build

    def __repr__(self) -> str:
        after = '' if self.initial is None else f'={self.initial!r}'
        return f"Declaration<{self.identity!r}{after}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        ret = [self.identity]
        if self.metadata is not None:
            ret.append(self.metadata)
        if self.initial is not None:
            ret.append(self.initial)
        return 'declaration', ret

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        from . import Scope, Statement
        identity: Identity
        id_stack: list[Identifier] = []
        metadata = None
        start: SourceLocation
        end: SourceLocation

        if (tok := stream.peek()) is not None and tok.type == TokenType.LBracket:
            start = stream.pop().location
            metadata = MetadataList.try_lex(stream)
            stream.expect(TokenType.RBracket)

        if (identity := Identity.try_lex(stream)) is None:
            # Maybe dotted?
            if (first_id := Identifier.try_lex(stream)) is None:
                return
            print(first_id)
            id_stack.append(first_id)
            start = tok.location
            while (tok := stream.peek()) is not None and tok.type == TokenType.Dot:
                stream.pop()
                if (next_id := Identifier.try_lex(stream)) is None:
                    raise LexError("Trailing Dot, expected `Identifier` or `Identity`.")
                id_stack.append(next_id)
                print(first_id, *id_stack, sep='.')
            stream.expect(TokenType.Colon)
            stream.expect(TokenType.NamespaceKeyword)
        else:
            start = identity.location

        if (tok := stream.peek()) is not None and tok.type == TokenType.Equals:
            stream.pop()

            if id_stack:
                stream.expect(TokenType.LBrace)
                decls = []
                while (tok := stream.peek()) is not None and tok.type != TokenType.RBrace:
                    if (decl := Declaration.try_lex(stream)) is None:
                        raise LexError("Expected `Declaration` or `}`")
                    decls.append(decl)
                    stream.expect(TokenType.Semicolon)
                end = stream.expect(TokenType.RBrace).location
                return Namespace([i.value for i in id_stack],
                                 decls,
                                 metadata,
                                 location=SourceLocation.from_to(start, end))
            elif id_stack:
                raise LexError("Only namespaces may be defined with multi-level names.")

            if (val := (Scope.try_lex(stream) or Expression.try_lex(stream))) is None:
                raise LexError("Expected a `Scope` or `Expression`!")

            end = val.location
            return cls(identity, val, metadata=metadata, location=SourceLocation.from_to(start, end))

        ret = cls(identity, val, metadata=metadata, location=SourceLocation.from_to(start, end))
        return ret

    """
    def check(self) -> None:
        if self.identity.rhs == 'namespace':
            return
        from . import _SCOPE, StaticType
        scope = _SCOPE.get()
        assert scope is not None

        decl_type = StaticType.from_type(self.identity.rhs)
        if self.metadata is not None:
            yield from self.metadata.check()
            for identifier in self.metadata.metadata:
                id_type = identifier.resolve_type()
                first_param = id_type.callable[0]
                if decl_type != first_param:
                    input(
                        f"\n\n\n\n\n{decl_type.callable[0] == first_param.callable[0]}\n{decl_type.callable[0]}\n{first_param.callable[0]}"
                    )
                    raise CompilerNotice(
                        'Error',
                        f"Metadata `{identifier.value}({first_param.name})` used on non-applicable type `{decl_type.name}`.",
                        identifier.location)
        yield from self.identity.check()

        if self.initial is not None:
            if self.identity.rhs.is_a(Type_) and self.identity.rhs.mods and self.identity.rhs.mods[-1].is_a(ParamList):
                plist: ParamList = self.identity.rhs.mods[-1]
                with _new_scope(self.identity.lhs.value) as scope:
                    for t in plist.params:
                        if scope.in_scope(t.lhs.value):
                            yield CompilerNotice("Warning", f"{t.lhs.value!r} shadows variable in parent scope.",
                                                 t.lhs.location)
                        scope.variables[t.lhs.value] = t.rhs
                    yield from self.initial.check()
    """
