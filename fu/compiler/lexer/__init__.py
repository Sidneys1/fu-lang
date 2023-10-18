from abc import ABC, abstractmethod
from typing import Any, Iterable, Optional, Union, Self, TypeAlias
from logging import getLogger
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass, field

from .. import CompilerNotice, ImmutableTokenStream, TokenStream
from ..tokenizer import TokenType, Token, SourceLocation, SpecialOperatorType, NON_CODE_TOKEN_TYPES
from ..stream import StreamExpectError, QuietStreamExpectError

_LOG = getLogger(__name__)

_FORMATTING_DEPTH: ContextVar[int] = ContextVar('_FORMATTING_DEPTH', default=0)
_TAB = '  '


def _tab():
    return _TAB * _FORMATTING_DEPTH.get()


@contextmanager
def _indent():
    depth = _FORMATTING_DEPTH.get()
    reset = _FORMATTING_DEPTH.set(depth + 1)
    try:
        yield _TAB * (depth + 1)
    finally:
        _FORMATTING_DEPTH.reset(reset)


class LexError(Exception):
    ...


class LexWarning(Warning):
    ...


def parse(istream: ImmutableTokenStream) -> Optional['Document']:
    try:
        return Document.try_lex(istream)
    except LexError as ex:
        _LOG.error("%sFailed to lex `Document`: %s", 'x ' * istream.depth, ex)
    except StreamExpectError as ex:
        expected = ex.expected.__name__ if isinstance(ex.expected, type) else repr(ex.expected)
        _LOG.error("%sFailed to lex `Document`: Expected %s, got %r", 'x ' * istream.depth, expected, ex.got)
    return None


@dataclass(repr=False, slots=True, frozen=True)
class Lex(ABC):
    """Base class for a lexical element."""

    raw: list[Union[Token, 'Lex']]
    location: SourceLocation = field(kw_only=True)

    @abstractmethod
    def to_code(self) -> Iterable[str]:
        ...

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Optional[Self]:
        _LOG.debug("%sTrying to lex `%s`", '| ' * istream.depth, cls.__name__)
        with istream.clone() as stream:
            try:
                ret = cls._try_lex(stream)
                if ret is not None:
                    stream.commit()
                    _LOG.debug("%sWas a `%s`!", 'y ' * istream.depth, cls.__name__)
                return ret
            except LexWarning as ex:
                _LOG.warn("%sFailed to lex `%s`: %s", 'x ' * istream.depth, cls.__name__, ex)
            # except EOFError as ex:
            #     _LOG.error("%sFailed to lex `%s`: Reached end of file", 'x ' * istream.depth, cls.__name__)
            except QuietStreamExpectError:
                pass
        return None

    def static_execute(self) -> Any:
        raise NotImplementedError(f"Type `{self.__class__.__name__}` does not implement `static_execute`!")

    @classmethod
    def expect(cls, istream: ImmutableTokenStream) -> 'Lex':
        ret = cls.try_lex(istream)
        if ret is None:
            raise LexError(f"Expected `{cls.__name__}`")
        return ret

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Optional['Lex']:
        ...

    def is_a(self, other: type) -> bool:
        return isinstance(self, other)

    def __repr__(self) -> str:
        value = getattr(self, 'value', None)
        inner = '' if value is None else repr(value)
        return f"{self.__class__.__name__}<{inner}>"

    def unrepr(self, s=None) -> None:
        if s is None:
            s = self.s_expr()
            print(s)
        p = 0
        build = ''
        children = self._s_expr()[1]
        while children:
            for child in children:
                if not isinstance(child, Lex):
                    continue
                r = child.s_expr()
                p = s.find(r, p)
                build += ' ' * (p - len(build))
                build += r
                p += len(r)
            if build != s and len(children) > 1:
                print(build)
            p = 0
            s = build
            build = ''
            children = [g for c in children if isinstance(c, Lex) for g in c._s_expr()[1]]

    def _s_expr(self) -> tuple[str, list['Lex']]:
        if isinstance(value := getattr(self, 'value', None), Lex):
            return self.__class__.__name__.lower(), [value]
        raise NotImplementedError(f"_s_expr not implemented for {self.__class__.__name__}")

    def s_expr(self) -> str:
        display, children = self._s_expr()
        if not children:
            return display
        return '(' + ' '.join(c.s_expr() if isinstance(c, Lex) else str(c) for c in [display] + children) + ')'


from .identifier import Identifier
from .lexed_literal import LexedLiteral
from .atom import Atom
from .operator import Operator
from .expression import Expression
from .return_statement import ReturnStatement
from .param_list import ParamList
from .generic_param_list import GenericParamList


@dataclass(repr=False, slots=True, frozen=True)
class ExpList(Lex):
    """CallList: Expression [',' Expression[...]];"""
    values: list[Expression]

    def __str__(self) -> str:
        inner = ', '.join(str(x) for x in self.values)
        return f"({inner})"

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.values)
        return f"CallList<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'params', self.values

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (tok := stream.peek()) is None or tok.type == TokenType.RParen or (first :=
                                                                              Expression.try_lex(stream)) is None:
            return

        params = [first]

        while (tok := stream.peek()) is not None and tok.type == TokenType.Comma and stream.pop() and (
                next := Expression.try_lex(stream)) is not None:
            params.append(next)

        return cls(params, location=SourceLocation.from_to(params[0].location, params[-1].location))


@dataclass(repr=False, slots=True, frozen=True)
class ArrayDef(Lex):
    """ArrayDef: '[' [Number] ']';"""
    size: Token | None

    def __str__(self) -> str:
        if self.size is not None:
            return f"[{self.size.value}]"
        return "[]"

    def __repr__(self) -> str:
        return str(self)

    def _s_expr(self) -> tuple[str, list[Self]]:
        return f"is-array", [self.size.value] if self.size else []

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        start = stream.expect(TokenType.LBracket, quiet=True).location
        size = None
        if stream.peek().type == TokenType.Number:
            size = stream.pop()
        end = stream.expect(TokenType.RBracket).location
        return cls(size, location=SourceLocation.from_to(start, end))


@dataclass(repr=False, slots=True, frozen=True)
class Type_(Lex):
    """Type_: Identifier [ ArrayDef | ParamList ]"""

    ident: Identifier
    mods: list[ParamList | ArrayDef | GenericParamList] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.mods:
            return self.ident.value
        mods = ''.join(str(m) for m in self.mods)
        return f"{self.ident}{mods}"

    def __repr__(self) -> str:
        mods = ''.join(repr(m) for m in self.mods) if self.mods else ''
        return f"Type_<{self.ident.value}, {mods}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "type", [self.ident] + self.mods

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (ident := Identifier.try_lex(stream)) is None:
            return None
        start = ident.location
        end = ident.location
        mods = []
        while True:
            mod: ParamList | ArrayDef | GenericParamList | None
            match stream.peek():
                case Token(type=TokenType.LParen):
                    mod = ParamList.try_lex(stream)
                case Token(type=TokenType.LBracket):
                    mod = ArrayDef.try_lex(stream)
                case Token(type=TokenType.LessThan):
                    mod = GenericParamList.try_lex(stream)
                case _:
                    break
            if mod is None:
                break
            end = mod.location
            mods.append(mod)
        return cls([ident, *mods], ident, mods, location=SourceLocation.from_to(start, end))


@dataclass(repr=False, slots=True, frozen=True)
class Namespace(Lex):
    """Doesn't parse itself, is parsed by Declaration."""
    name: list[Identifier]
    """Namespace name (may represent multiple nested namespaces)."""
    static_scope: 'StaticScope'

    # metadata: Optional['MetadataList']

    def to_code(self) -> Iterable[str]:
        # if self.metadata:
        #     yield self.metadata.to_code()

        yield _tab() + '.'.join(x.value for x in self.name) + ': namespace = '
        yield from self.static_scope.to_code()
        yield ';'

        # first_line = _tab() + '.'.join(x.value for x in self.name) + ': namespace = {'
        # if not self.static_scope.content:
        #     yield first_line + ' };'
        # else:
        #     yield first_line
        #     with _indent():
        #         for x in self.static_scope.to_code():
        #             yield x
        #     yield _tab() + '};'

    def __str__(self) -> str:
        name = '.'.join(x.value for x in self.name)
        if not self.static_scope:
            return f"{name}: namespace = {{}};"
        with _indent() as tab:
            inner = tab + f'\n{tab}'.join(str(x) for x in self.static_scope)
        return f"{name}: namespace = {{\n{inner}\n{_tab()}}}"

    def __repr__(self) -> str:
        # before = '' if self.metadata is None else f"{self.metadata!r}, "
        after = '' if not self.static_scope else f", {', '.join(repr(x) for x in self.static_scope)}"
        return f"Namespace<{'.'.join(i.value for i in self.name)}{after}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return f"namespace:{'.'.join(i.value for i in self.name)}", [x for x in self.static_scope]


@dataclass(repr=False, slots=True, frozen=True)
class SpecialOperatorIdentity(Lex):
    """SpecialOperatorIdentity: SpecialOperator ':' Type_;"""
    lhs: SpecialOperatorType
    rhs: Type_

    def to_code(self) -> Iterable[str]:
        yield f"{self.lhs.value}: {self.rhs}"

    def __repr__(self) -> str:
        return f"SpecialOperator<{self.lhs!r}, {self.rhs!r}>"

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return self.lhs.value, [self.rhs]


@dataclass(repr=False, slots=True, frozen=True)
class Identity(Lex):
    """Identity: Identifier ':' Type_"""
    lhs: Identifier
    rhs: Type_

    # def __str__(self) -> str:
    #     return f"{self.lhs}: {self.rhs}"

    def to_code(self) -> Iterable[str]:
        yield _tab() + self.lhs.value + ': ' + ''.join(self.rhs.to_code())

    def __repr__(self) -> str:
        return f"Identity<{self.lhs!r}, {self.rhs!r}>"

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return f"identity", [self.lhs, self.rhs]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        raw: list[Lex | Token] = []
        tok = stream.pop()
        if tok is None or tok.type not in (TokenType.Word, TokenType.SpecialOperator):
            return None
        raw.append(tok)

        lhs = (Identifier(raw, tok.value, location=tok.location) if tok.type == TokenType.Word else tok)
        assert lhs is not None and (isinstance(lhs, Token) or isinstance(lhs, Identifier))
        raw.append(lhs)

        if (tok := stream.pop()) is None or tok.type != TokenType.Colon:
            raise LexWarning("Expected Colon")
        raw.append(tok)

        if stream.peek().type == TokenType.NamespaceKeyword:
            return None

        rhs = Type_.try_lex(stream)
        if rhs is None:
            raise LexError("Expected a `Type_`.")
        raw.append(rhs)

        location = SourceLocation.from_to(raw[0].location, raw[-1].location)

        if isinstance(lhs, Identifier):
            return Identity(raw, lhs, rhs, location=location)

        return SpecialOperatorIdentity(raw, lhs.special_op_type, rhs, location=location)


# MetadataList
"""
@dataclass(repr=False, slots=True, frozen=True)
class MetadataList(Lex):
    \"""MetadataList: Identifier (',' Identifier)*\"""
    metadata: list[Identifier] = field(default_factory=list)

    def __str__(self) -> str:
        return f'{", ".join(str(m) for m in self.metadata)}'

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "metadata", self.metadata

    @classmethod
    def _try_lex(cls, stream: TokenStream):
        ident = Identifier.try_lex(stream)
        if ident is None:
            raise LexError("Metadata list expects at least one `Identifier`.")
        start = ident.location
        end = ident.location
        meta = [ident]
        tok = stream.peek()
        while tok is not None and tok.type == TokenType.Comma:
            stream.pop()
            if (id := Identifier.try_lex(stream)) is None:
                raise LexError("Expected `Identifier` after ','.")
            end = id.location
            meta.append(id)
            tok = stream.peek()
        return cls(meta, location=SourceLocation.from_to(start, end))
"""

from .declaration import Declaration, TypeDeclaration


@dataclass(repr=False, slots=True, frozen=True)
class Statement(Lex):
    """Statement: Declaration | Expression;"""
    value: 'Expression'

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Expression]

    def __str__(self) -> str:
        return f'{_tab()}{self.value};\n'

    def __repr__(self) -> str:
        return f"Statement<{self.value!r}>"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        for t in cls.allowed:
            if (res := t.try_lex(stream)) is not None:
                break
        if res is None:
            return
        end = stream.expect(TokenType.Semicolon)
        return cls(res, location=SourceLocation.from_to(res.location, end.location))


ALLOWED_IN_STATIC_SCOPE: TypeAlias = Declaration


@dataclass(repr=False, slots=True, frozen=True)
class StaticScope(Lex):
    """StaticScope: Declaration[, Declaration]*;"""

    content: list[ALLOWED_IN_STATIC_SCOPE]

    def to_code(self):
        if len(self.raw) == 2:
            yield '{ }'
            return

        yield '{'
        with _indent():
            for x in self.raw[1:-1]:
                if isinstance(x, Lex):
                    yield from x
                elif x.type == TokenType.BlankLine:
                    yield x.value
                else:
                    yield _tab() + x.value
        yield '}'
        # if not self.content:
        #     yield '{ }'
        #     return
        # yield '{'
        # yield from (_tab() + c.to_code() for c in self.content)
        # yield _tab() + '}'

    def __repr__(self) -> str:
        inner = ", ".join(repr(c) for c in self.content)
        return f"StaticScope<{inner}>"

    def __iter__(self):
        return self.content.__iter__()

    def _s_expr(self) -> tuple[str, list[Lex]]:
        return None, self.content

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        lbrace = stream.expect(TokenType.LBrace)
        raw: list[Lex | Token] = [lbrace]

        ret: list[ALLOWED_IN_STATIC_SCOPE] = []
        while (tok := stream.peek()) is not None and tok.type != TokenType.RBrace:
            if tok.type in NON_CODE_TOKEN_TYPES:
                raw.append(stream.pop())
                continue
            if (decl := Declaration.try_lex(stream)) is None:
                raise LexError("Expected `Declaration`.")
            ret.append(decl)
            raw.append(decl)
        rbrace = stream.expect(TokenType.RBrace)
        raw.append(rbrace)

        return StaticScope(raw, ret, location=SourceLocation.from_to(raw[0].location, raw[-1].location))


@dataclass(repr=False, slots=True, frozen=True)
class Scope(Lex):
    """Scope: '{' (Statement | ReturnStatement)* '}';"""
    content: list[Union['ReturnStatement', 'Statement', Declaration]]

    def __str__(self) -> str:
        with _indent():
            inner = ''.join(str(x) for x in self.content)
        if not inner:
            return '{ }'
        return '{\n' + inner + _tab() + '}'

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.content)
        return f"Scope<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "scope", self.content

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        start = stream.expect(TokenType.LBrace, quiet=True)
        ret = []
        while not stream.eof:
            match stream.peek().type:
                case TokenType.RBrace:
                    end = stream.pop()
                    return cls(ret, location=SourceLocation.from_to(start.location, end.location))
                case TokenType.ReturnKeyword:
                    ret.append(ReturnStatement.try_lex(stream))
                    continue
                case _:
                    if (res := Declaration.try_lex(stream)) is None and (res := Statement.try_lex(stream)) is None:
                        raise LexError("Expected `Statement` or `Declaration`!")
                    ret.append(res)
                    continue

        end = stream.expect(TokenType.RBrace)
        return cls(ret, location=SourceLocation.from_to(start.location, end.location))


ALLOWED_AT_TOP_LEVEL: TypeAlias = Declaration | TypeDeclaration | Namespace


@dataclass(repr=False, slots=True, frozen=True)
class Document(Lex):
    """Document: Declaration* EOF;"""
    content: list[ALLOWED_AT_TOP_LEVEL]

    def __str__(self) -> str:
        return ''.join(self.to_code())
        # return ''.join(str(s) for s in self.content)

    def to_code(self) -> Iterable[str]:
        for x in self.raw:
            if isinstance(x, Lex):
                yield from x.to_code()
            else:
                yield x.value

    def __repr__(self) -> str:
        inner = ', '.join(repr(s) for s in self.content)
        return f"Document<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'document', self.content

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        raw: list[Token | Lex] = []

        declarations: list[ALLOWED_AT_TOP_LEVEL] = []
        while True:
            tok = stream.peek()
            _LOG.debug(f"In document gettin a {tok}")
            if tok.type == TokenType.EOF:
                break
            if tok.type in NON_CODE_TOKEN_TYPES:
                raw.append(stream.pop())
                continue
            _LOG.debug(f"In document looking for a Decl")
            if (res := Declaration.try_lex(stream)) is None:
                break
            declarations.append(res)
            raw.append(res)

        stream.expect(TokenType.EOF)

        if not declarations:
            location = SourceLocation((0, 0), (1, 1), (1, 1))
        else:
            location = SourceLocation.from_to(raw[0].location, raw[-1].location)

        return Document(raw, declarations, location=location)
