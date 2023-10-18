from typing import Union, Self, TYPE_CHECKING, Union, Literal as Literal_
from dataclasses import dataclass

from .. import TokenStream
from ..tokenizer import SourceLocation, TokenType, Token

from . import (Identifier, Identity, Lex, LexError, Namespace, Type_, SpecialOperatorIdentity, _indent, _tab, ExpList,
               GenericParamList)

if TYPE_CHECKING:
    from . import Scope, Expression


@dataclass(repr=False, slots=True, frozen=True)
class TypeDeclaration(Lex):
    name: Identifier
    type: Literal_['interface'] | Literal_['type']
    definition: Type_ | list[Union['Declaration', 'TypeDeclaration']] | None = None
    generic_params: GenericParamList | None = None

    def _s_expr(self) -> tuple[str, list[Self]]:
        if self.definition is None:
            return "typedecl", []
        return "typedecl", [self.name] + (self.definition if isinstance(self.definition, list) else [self.definition])

    def __str__(self) -> str:
        build = ''

        # if self.metadata:
        #     build += f"[{self.metadata}]\n{_tab()}"

        build += str(self.name) + ': type'

        if self.definition is None:
            return build + ';\n'
        if isinstance(self.definition, Type_):
            return f"{build} = {self.definition};\n"
        build += ' = {\n'
        with _indent():
            inner = _tab() + _tab().join(str(x) for x in self.definition)
        return build + inner + _tab() + '};\n'

    def __repr__(self) -> str:
        after = '' if self.definition is None else f'={self.definition!r}'
        return f"TypeDeclaration<{self.name!r}{after}>"


@dataclass(repr=False, slots=True, frozen=True)
class Declaration(Lex):
    """Declaration: Identity [ '=' Expression | Scope ];"""
    identity: Identity | SpecialOperatorIdentity
    initial: Union['Scope', 'Expression', ExpList, None] = None

    # metadata: MetadataList | None = None

    def __str__(self) -> str:
        from . import Scope, Statement
        if self.identity is not None and self.identity.rhs == 'namespace' and isinstance(self.initial, Scope) and len(
                self.initial.content) == 1 and isinstance(self.initial.content[0], Statement) and isinstance(
                    self.initial.content[0].value,
                    Declaration) and self.initial.content[0].value.identity.rhs == 'namespace':
            return f"{self.identity.lhs}.{self.initial.content[0].value}"

        build = ''

        # if self.metadata:
        #     build += f"[{self.metadata}]\n{_tab()}"

        build += str(self.identity)

        if self.initial is not None:
            build += f" = {self.initial}"
        return build + ';\n'

    def __repr__(self) -> str:
        after = '' if self.initial is None else f'={self.initial!r}'
        return f"Declaration<{self.identity!r}{after}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        ret = [self.identity]
        # if self.metadata is not None:
        #     ret.append(self.metadata)
        if self.initial is not None:
            ret.append(self.initial)
        return 'declaration', ret

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        from . import Scope, Expression

        raw: list[Lex, Token] = []

        identity: Identity | None
        id_stack: list[Identifier] = []
        # metadata = None
        start: SourceLocation
        end: SourceLocation
        initial = None

        # if (tok := stream.peek()) is not None and tok.type == TokenType.LBracket:
        #     start = stream.pop().location
        #     metadata = MetadataList.try_lex(stream)
        #     stream.expect(TokenType.RBracket)

        if (identity := Identity.try_lex(stream)) is None:
            # Maybe dotted?
            if (first_id := Identifier.try_lex(stream)) is None:
                return None
            raw.append(first_id)
            # print(first_id)
            id_stack.append(first_id)
            start = first_id.location
            while (tok := stream.peek()) is not None and tok.type == TokenType.Dot:
                raw.append(stream.pop())
                if (next_id := Identifier.try_lex(stream)) is None:
                    raise LexError("Trailing Dot, expected `Identifier` or `Identity`.")
                id_stack.append(next_id)
                raw.append(next_id)
                # print(first_id, *id_stack, sep='.')
            if (tok := stream.peek()) is None or tok.type != TokenType.Colon:
                return None
            raw.append(stream.expect(TokenType.Colon))
            if (tok := stream.pop()) is None:
                return None
            if tok.type != TokenType.NamespaceKeyword:
                return None
            raw.append(tok)
            raw.append(stream.expect(TokenType.Equals))
            from . import StaticScope
            static_scope = StaticScope.try_lex(stream)
            assert static_scope is not None
            raw.append(static_scope)
            tok = stream.expect(TokenType.Semicolon)
            raw.append(tok)
            end = tok.location
            return Namespace(raw, id_stack, static_scope, location=SourceLocation.from_to(start, end))

        start = identity.location
        raw.append(identity)

        if identity.rhs.ident.value in ('type', 'interface'):
            if len(id_stack) > 1:
                return None
            if (tok := stream.pop()) is None:
                return None
            raw.append(tok)

            if len(identity.rhs.mods) > 1 or any(not isinstance(m, GenericParamList) for m in identity.rhs.mods):
                return None

            generic_mod = identity.rhs.mods[0] if identity.rhs.mods else None

            if tok.type == TokenType.Semicolon:
                return TypeDeclaration(raw,
                                       identity.lhs,
                                       identity.rhs.ident.value,
                                       location=SourceLocation.from_to(start, tok.location))
            if tok.type != TokenType.Equals:
                return None
            # Either a Type_ or a body.
            if (tok := stream.peek()) is not None and tok.type == TokenType.LBrace:
                raw.append(stream.pop())
                inner: list[Declaration | TypeDeclaration] = []
                while (lex := Declaration.try_lex(stream)) is not None:
                    inner.append(lex)
                    raw.append(lex)
                raw.append(stream.expect(TokenType.RBrace))
            elif (type_ := Type_.try_lex(stream)) is None:
                return None

            inner = type_
            raw.append(type_)

            end = stream.expect(TokenType.Semicolon).location
            return TypeDeclaration(raw,
                                   identity.rhs.ident.value,
                                   inner,
                                   generic_mod,
                                   location=SourceLocation.from_to(start, end))

        if (tok := stream.peek()) is not None and tok.type == TokenType.Equals:
            stream.pop()
            if (tok := stream.peek()) is not None and tok.type == TokenType.LParen:
                stream.pop()
                exp_list = ExpList.try_lex(stream)
                if exp_list is None:
                    raise LexError("Expected an `ExpList`!")
                stream.expect(TokenType.RParen)
                initial = exp_list
            elif (initial := (Scope.try_lex(stream) or Expression.try_lex(stream))) is None:
                raise LexError("Expected a `Scope` or `Expression`!")

        end = stream.expect(TokenType.Semicolon).location

        ret = cls(identity, initial, location=SourceLocation.from_to(start, end))
        return ret
