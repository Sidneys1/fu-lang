from typing import Iterable, Union, Self, TYPE_CHECKING, Union, Literal as Literal_
from dataclasses import dataclass

from .. import TokenStream
from ..tokenizer import SourceLocation, TokenType, Token, NON_CODE_TOKEN_TYPES

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

    def to_code(self) -> Iterable[str]:
        yield self.name.value
        yield f": {self.type}"
        if self.generic_params is not None:
            yield from self.generic_params.to_code()
        if self.definition is None:
            yield ';'
            return
        yield ' = '
        if isinstance(self.definition, Type_):
            yield from self.definition.to_code()
        elif isinstance(self.definition, list):
            lbracket = next((x for x in self.raw if isinstance(x, Token) and x.type == TokenType.LBrace), None)
            assert lbracket is not None
            lindex = self.raw.index(lbracket)
            rbracket = next((x for x in reversed(self.raw) if isinstance(x, Token) and x.type == TokenType.RBrace),
                            None)
            assert rbracket is not None
            rindex = self.raw.index(rbracket)
            if rindex == lindex + 1:
                yield '{ }'
            else:
                yield '{'
                with _indent() as tab:
                    for x in self.raw[lindex + 1:rindex]:
                        if isinstance(x, Lex):
                            yield from x.to_code()
                        elif x.type == TokenType.BlankLine:
                            yield x.value
                        else:
                            yield tab + x.value
                yield '}'
        else:
            assert False, "Should never happen"
        yield ';'
        # for x in self.raw:
        #     if isinstance(x, Lex):
        #         yield from x.to_code()
        #     else:
        #         yield x.value
        # yield f"{self.name.value}: {self.type}"
        # if isinstance(self.definition, Type_):
        #     yield from self.definition.to_code()
        # elif isinstance(self.definition, list):
        #     # yield from
        # yield ';'

    def _s_expr(self) -> tuple[str, list[Self]]:
        if self.definition is None:
            return "typedecl", []
        return "typedecl", [self.name] + (self.definition if isinstance(self.definition, list) else [self.definition])

    def __repr__(self) -> str:
        after = '' if self.definition is None else f'={self.definition!r}'
        return f"TypeDeclaration<{self.name!r}{after}>"


@dataclass(repr=False, slots=True, frozen=True)
class Declaration(Lex):
    """Declaration: Identity [ '=' Expression | Scope ];"""
    identity: Identity | SpecialOperatorIdentity
    initial: Union['Scope', 'Expression', ExpList, None] = None

    def to_code(self) -> Iterable[str]:
        yield from self.identity.to_code()
        if self.initial is not None:
            yield ' = '
            yield from self.initial.to_code()
        yield ';'

    # metadata: MetadataList | None = None

    # def __str__(self) -> str:
    #     from . import Scope, Statement
    #     if self.identity is not None and self.identity.rhs == 'namespace' and isinstance(self.initial, Scope) and len(
    #             self.initial.content) == 1 and isinstance(self.initial.content[0], Statement) and isinstance(
    #                 self.initial.content[0].value,
    #                 Declaration) and self.initial.content[0].value.identity.rhs == 'namespace':
    #         return f"{self.identity.lhs}.{self.initial.content[0].value}"

    #     build = ''

    #     # if self.metadata:
    #     #     build += f"[{self.metadata}]\n{_tab()}"

    #     build += str(self.identity)

    #     if self.initial is not None:
    #         build += f" = {self.initial}"
    #     return build + ';\n'

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
            raw.append(stream.expect(TokenType.Semicolon))
            return Namespace(raw,
                             id_stack,
                             static_scope,
                             location=SourceLocation.from_to(raw[0].location, raw[-1].location))

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
                                       location=SourceLocation.from_to(raw[0].location, raw[-1].location))
            if tok.type != TokenType.Equals:
                return None
            # Either a Type_ or a body.
            if (tok := stream.peek()) is not None and tok.type == TokenType.LBrace:
                raw.append(stream.pop())
                inner: list[Declaration | TypeDeclaration] = []
                while True:
                    tok = stream.peek()
                    if tok.type == TokenType.RBrace:
                        break
                    if tok.type in NON_CODE_TOKEN_TYPES:
                        raw.append(stream.pop())
                        continue
                    if (lex := Declaration.try_lex(stream)) is None:
                        break
                    inner.append(lex)
                    raw.append(lex)
                raw.append(stream.expect(TokenType.RBrace))
            elif (type_ := Type_.try_lex(stream)) is None:
                return None
            else:
                inner = type_
                raw.append(inner)

            raw.append(stream.expect(TokenType.Semicolon))
            return TypeDeclaration(raw,
                                   identity.lhs,
                                   identity.rhs.ident.value,
                                   inner,
                                   generic_mod,
                                   location=SourceLocation.from_to(raw[0].location, raw[-1].location))

        if (tok := stream.peek()) is not None and tok.type == TokenType.Equals:
            raw.append(stream.pop())
            if (tok := stream.peek()) is not None and tok.type == TokenType.LParen:
                raw.append(stream.pop())
                exp_list = ExpList.try_lex(stream)
                if exp_list is None:
                    raise LexError("Expected an `ExpList`!")
                raw.append(exp_list)
                raw.append(stream.expect(TokenType.RParen))
                initial = exp_list
            elif (initial := (Scope.try_lex(stream) or Expression.try_lex(stream))) is None:
                raise LexError("Expected a `Scope` or `Expression`!")
            else:
                raw.append(initial)

        raw.append(tok := stream.expect(TokenType.Semicolon))

        ret = Declaration(raw, identity, initial, location=SourceLocation.from_to(raw[0].location, raw[-1].location))
        return ret
