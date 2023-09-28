from abc import ABC
from typing import Any, Iterable, Optional, Union, Self, Literal as Literal_, Iterator, ClassVar
from logging import getLogger
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass as _dataclass, field

from .. import CompilerNotice, MODULE_LOGGER
from ..tokenizer import TokenType, Token, TokenStream, ImmutableTokenStream, SourceLocation
from ..stream import StreamExpectError, QuietStreamExpectError

_LOG = MODULE_LOGGER.getChild(__name__)

_FORMATTING_DEPTH: ContextVar[int] = ContextVar('_FORMATTING_DEPTH', default=0)
_TAB = '  '
"""
@_dataclass(frozen=True, slots=True, kw_only=True)
class ScopeContext:
    name: str
    variables: dict[str, Union[StaticType, 'Type_']] = field(default_factory=dict, kw_only=True)
    parent: Self | None = field(default=None, kw_only=True)

    @property
    def fqdn(self) -> str:
        s = self
        r = self.name
        while s is not None:
            r = f"{s.name}.{r}"
            s = s.parent
        return r

    @contextmanager
    def merge(self, other: dict[str, StaticType]):
        cur = _SCOPE.get()
        val = ScopeContext(name=None, parent=cur)
        token = _SCOPE.set(val)
        try:
            _LOG.debug(f"Merging {other} in")
            val.variables.update(other)
            yield val
        finally:
            _SCOPE.reset(token)

    def in_scope(self, identifier: str) -> Optional[StaticType]:
        _LOG.debug(f'Searching for {identifier!r} in {self}')
        s = self
        while s:
            if identifier in s.variables:
                ret = s.variables[identifier]
                if isinstance(ret, Type_):
                    ret = StaticType.from_type(ret)
                    if ret is not None:
                        s.variables[identifier] = ret
                return ret
            s = s.parent
        _LOG.critical(f"Could not resolve runtime identifier {identifier}")


_SCOPE: ContextVar[ScopeContext | None] = ContextVar('_SCOPE', default=None)



@contextmanager
def _new_scope(name: str):
    cur = _SCOPE.get()
    val = ScopeContext(name=name, variables=_BUILTINS) if cur is None else ScopeContext(name=name, parent=cur)
    token = _SCOPE.set(val)
    try:
        yield val
    finally:
        _SCOPE.reset(token)
"""

lex_dataclass = _dataclass(repr=False, slots=True, frozen=True)


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


@lex_dataclass
class Lex(ABC):
    """Base class for a lexical element."""

    location: SourceLocation | None = field(kw_only=True, default=None)

    @classmethod
    def try_lex(cls, istream: ImmutableTokenStream) -> Optional['Lex']:
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
            except EOFError as ex:
                _LOG.error("%sFailed to lex `%s`: Reached end of file", 'x ' * istream.depth, cls.__name__)
            except QuietStreamExpectError:
                pass

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

    def resolve_type(self) -> Optional['StaticType']:
        raise NotImplementedError(f"`resolve_type` is not implemented on `{self.__class__.__name__}` ({self!r})")

    def is_a(self, other: type) -> bool:
        return isinstance(self, other)

    def check(self) -> Iterator[CompilerNotice]:
        yield CompilerNotice('Note', f'{self.__class__.__name__} does not implement "check()"!', self.location)
        if False:
            yield

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

    def _s_expr(self) -> tuple[str, list[Self]]:
        if isinstance(value := getattr(self, 'value', None), Lex):
            return self.__class__.__name__.lower(), [value]
        raise NotImplementedError(f"_tree not implemented for {self.__class__.__name__}")

    def s_expr(self) -> str:
        display, children = self._s_expr()
        if not children:
            return display
        return '(' + ' '.join(c.s_expr() if isinstance(c, Lex) else str(c) for c in [display] + children) + ')'


@lex_dataclass
class Identifier(Lex):
    """Identifier: Word"""
    value: str

    def __str__(self) -> str:
        return self.value

    def _s_expr(self) -> tuple[str, list[Self]]:
        return f'"{self.value}"', []

    def resolve_type(self) -> Optional['StaticType']:
        ret = _SCOPE.get().in_scope(self.value)
        _LOG.debug(f"Resolved {self} to {ret}")
        return ret

    def check(self) -> Iterator[CompilerNotice]:
        # todo: check that this identifier is in scope
        scope = _SCOPE.get()
        if not scope.in_scope(self.value):
            s = scope
            while s:
                print(s.variables)
                s = s.parent
            yield CompilerNotice("Error", f"{self.value!r} has not yet been defined.", self.location)
        if False:
            yield None

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        tok = stream.expect(TokenType.Word)
        return cls(tok.value, location=tok.location)


@lex_dataclass
class Literal(Lex):
    value: str
    type: TokenType

    def __str__(self) -> str:
        if self.type == TokenType.String:
            return f'"{self.value}"'
        return self.value

    def check(self) -> Iterator[CompilerNotice]:
        if False:
            yield None

    def resolve_type(self) -> Optional['StaticType']:
        scope = _SCOPE.get()
        assert scope is not None
        match self.type:
            case TokenType.String:
                return scope.in_scope('str')
            case TokenType.Number:
                return scope.in_scope('int')  # TODO: wut
            case _:
                raise NotImplementedError(f"`resolve_type` not implemented for {self!r}")

    def _s_expr(self) -> tuple[str, list[Self]]:
        return str(self), []


@lex_dataclass
class Atom(Lex):
    """Atom: Literal | Identifier | '(' Expression ')'"""
    value: Union[Literal, Identifier, 'Expression']

    def __str__(self) -> str:
        return f"({self.value})"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (x := stream.peek()) is not None and x.type == TokenType.LParen:
            start = stream.pop().location
            if (body := Expression.try_lex(stream)) is None:
                raise LexError("Expected `Expression`.")
            end = stream.expect(TokenType.RParen).location
            return cls(body, location=SourceLocation.from_to(start, end))

        if not stream.eof and stream.peek().type in (TokenType.String, TokenType.Number):
            tok = stream.pop()
            return Literal(tok.value, tok.type, location=tok.location)

        return Identifier.try_lex(stream)


from .operator import Operator


@lex_dataclass
class Expression(Lex):
    """Expression := Operator | Atom;"""
    value: Union[Operator, 'Atom']

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Expression<{self.value!r}>"

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Operator, Atom]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        for t in cls.allowed:
            if (ret := t.try_lex(stream)) is not None:
                return ret

    def check(self):
        yield from self.value.check()


@lex_dataclass
class ReturnStatement(Lex):
    """ReturnStatement: 'return' Expression;"""
    value: 'Expression'

    def __str__(self) -> str:
        return f"{_tab()}return {self.value};\n"

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        start = stream.expect(TokenType.ReturnKeyword, quiet=True).location
        value = Expression.try_lex(stream)
        end = stream.expect(TokenType.Semicolon).location
        return cls(value, location=SourceLocation.from_to(start, end))

    def check(self):
        _LOG.debug("checking returnstatement")
        yield from self.value.check()


@lex_dataclass
class ParamList(Lex):
    """ParamList: '(' Identity [',' Identity[...]] ')';"""
    params: list['Identity']

    def __str__(self) -> str:
        inner = ', '.join(str(x) for x in self.params)
        return f"({inner})"

    def __repr__(self) -> str:
        inner = ', '.join(repr(x) for x in self.params)
        return f"Paramlist<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'callable', self.params

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        start = stream.expect(TokenType.LParen, quiet=True).location

        if stream.peek().type == TokenType.RParen:
            end = stream.pop().location
            return cls([], location=SourceLocation.from_to(start, end))

        if (first := Identity.try_lex(stream)) is None:
            raise LexError("Expected Identity.")

        params = [first]
        while stream.peek().type == TokenType.Comma:
            stream.pop()
            if (next := Identity.try_lex(stream)) is None:
                raise LexError("Expected Identity.")
            params.append(next)

        end = stream.expect(TokenType.RParen).location
        return cls(params, location=SourceLocation.from_to(start, end))

    def check(self):
        for param in self.params:
            yield from param.check()


@lex_dataclass
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

    def check(self):
        for param in self.values:
            yield from param.check()


@lex_dataclass
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

    def check(self):
        if self.size and '.' in self.size.value:
            yield CompilerNotice('Error', "Array sizes cannot be decimals.", self.location)


@lex_dataclass
class Type_(Lex):
    """Type_: Identifier [ ArrayDef | ParamList ]"""

    ident: Identifier
    mods: list[ParamList | ArrayDef] = field(default_factory=list)

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
            return
        start = ident.location
        end = ident.location
        mods = []
        while (mod := (ParamList.try_lex(stream) or ArrayDef.try_lex(stream))) is not None:
            end = mod.location
            mods.append(mod)
        return cls(ident, mods, location=SourceLocation.from_to(start, end))

    def check(self):
        scope = _SCOPE.get()
        print('!!!checking', self.ident.value, 'in', scope.variables)
        if not scope.in_scope(self.ident.value):
            yield CompilerNotice("Error", f"{self.ident.value!r} has not yet been defined.", self.ident.location)
        # yield from self.ident.check()
        for mod in self.mods:
            yield from mod.check()


@lex_dataclass
class Namespace(Lex):
    """Doesn't parse itself, is parsed by Declaration."""
    name: list[str]
    """Namespace name (may represent multiple nested namespaces)."""
    declarations: list['Declaration']
    metadata: Optional['MetadataList']

    def __str__(self) -> str:
        name = '.'.join(self.name)
        if not self.declarations:
            return f"{name}: namespace = {{}};"
        with _indent() as tab:
            inner = tab + f'\n{tab}'.join(str(x) for x in self.declarations)
        return f"{name}: namespace = {{\n{inner}\n{_tab()}}}"

    def __repr__(self) -> str:
        before = '' if self.metadata is None else f"{self.metadata!r}, "
        after = '' if not self.declarations else f", {', '.join(repr(x) for x in self.declarations)}"
        return f"Namespace<{before}{'.'.join(self.name)}{after}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "namespace", [".".join(
            self.name)] + ([] if self.metadata is None else [".".join(self.name), self.metadata]) + self.declarations


@lex_dataclass
class Identity(Lex):
    """Identity: Identifier ':' ('namespace' | Type_);"""
    lhs: Identifier
    rhs: Type_

    def __str__(self) -> str:
        return f"{self.lhs}: {self.rhs}"

    def __repr__(self) -> str:
        return f"Identity<{self.lhs!r}, {self.rhs!r}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return f"identity", [self.lhs, self.rhs]

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        if (lhs := Identifier.try_lex(stream)) is None:
            return
        start = lhs.location
        if (tok := stream.pop()) is None or tok.type != TokenType.Colon:
            raise LexWarning("Expected Colon")
        if stream.peek().type == TokenType.NamespaceKeyword:
            return
        rhs = Type_.try_lex(stream)
        if rhs is None:
            raise LexError("Expected a `Type_`.")
        end = rhs.location

        return cls(lhs, rhs, location=SourceLocation.from_to(start, end))

    def check(self) -> None:
        scope = _SCOPE.get()
        # yield from self.lhs.check()
        if isinstance(self.rhs, Lex):
            yield from self.rhs.check()


@lex_dataclass
class MetadataList(Lex):
    """MetadataList: Identifier (',' Identifier)*"""
    metadata: list[Identifier] = field(default_factory=list)

    def __str__(self) -> str:
        return f'{", ".join(str(m) for m in self.metadata)}'

    def _s_expr(self) -> tuple[str, list[Self]]:
        return "metadata", self.metadata

    def check(self) -> Iterator[CompilerNotice]:
        scope = _SCOPE.get()
        for i in self.metadata:
            yield from i.check()
            type = scope.in_scope(i.value)
            if type is None:
                raise CompilerNotice("Error", f"Could not resolve `{i.value}`.", i.location)
            if not type.callable or type.evals_to != _VOID_TYPE:
                raise CompilerNotice("Error", "Metadata functions must be callable and return `void`.", i.location)

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


from .declaration import Declaration


@lex_dataclass
class Statement(Lex):
    """Statement: Declaration | Expression;"""
    value: Union['Expression', 'Declaration']

    @classmethod
    @property
    def allowed(self) -> Iterable[type[Lex]]:
        return [Declaration, Expression]

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

    def check(self) -> None:
        _LOG.debug("Checking statement %r", self.value)
        try:
            yield from self.value.check()
        except CompilerNotice as ex:
            yield ex


@lex_dataclass
class Scope(Lex):
    """Scope: '{' (Statement | ReturnStatement)* '}';"""
    content: list['ReturnStatement', 'Statement']

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
                    if (res := Statement.try_lex(stream)) is None:
                        raise LexError("Expected `Statement`!")
                    ret.append(res)
                    continue

        end = stream.expect(TokenType.RBrace)
        return cls(ret, location=SourceLocation.from_to(start.location, end.location))

    def check(self):
        if not self.content:
            yield CompilerNotice("Info", "Empty scope?", self.location)
            return
        with _new_scope('') as scope:
            # First populate
            _LOG.debug("populating scope")
            for statement in self.content:
                if statement.value.is_a(Declaration):
                    scope.variables.append(statement.value.identity.lhs)
                    if statement.value.initial is not None and not statement.value.initial.is_a(Scope):
                        statement.value.initial.check()
                else:
                    _LOG.debug("Checking statement %r", statement)
                    yield from statement.check()
            # Then check nested scopes
            _LOG.debug("Checking nested scopes")
            for statement in self.content:
                if statement.value.is_a(
                        Declaration) and statement.value.initial is not None and statement.value.initial.is_a(Scope):
                    yield from statement.check()

            # last = self.content[-1]
            # for statement in self.content:
            #     yield from statement.check()
            #     if isinstance(statement, ReturnStatement) and statement is not last:
            #         yield CompilerNotice("Error", "Scope contains multiple top-level return statments", statement.location)


@lex_dataclass
class Document(Lex):
    """Document: Declaration* EOF;"""
    declarations: list[Declaration | Namespace]

    def __str__(self) -> str:
        return ''.join(str(s) + ";\n" for s in self.declarations)

    def __repr__(self) -> str:
        inner = ', '.join(repr(s) for s in self.declarations)
        return f"Document<{inner}>"

    def _s_expr(self) -> tuple[str, list[Self]]:
        return 'document', self.declarations

    @classmethod
    def _try_lex(cls, stream: TokenStream) -> Lex | None:
        declarations: list[Declaration] = []
        while (res := Declaration.try_lex(stream)):
            declarations.append(res)
            stream.expect(TokenType.Semicolon)

        if not stream.eof:
            return None

        if not declarations:
            location = SourceLocation((0, 0), (1, 1), (1, 1), stream)
        else:
            location = SourceLocation.from_to(declarations[0].location, declarations[-1].location)

        return cls(declarations, location=location)

    def check(self):
        with _new_scope('') as scope:
            # First populate
            _LOG.debug("Populating document scope")
            for statement in self.declarations:
                if not isinstance(statement.value, Declaration):
                    yield CompilerNotice("Error", f"Documents can only contain Declarations.", statement.location)
                else:
                    if scope.in_scope(statement.value.identity.lhs.value):
                        yield CompilerNotice(
                            "Warning",
                            f"{statement.value.identity.lhs.value!r} is shadowing an identifier from the parent scope!",
                            statement.value.identity.lhs.location)
                    scope.variables[statement.value.identity.lhs.value] = statement.value.identity.rhs
                    if statement.value.initial is not None and not statement.value.initial.is_a(Scope):
                        statement.value.initial.check()
            # Then check nested scopes
            for statement in self.declarations:
                if statement.value.is_a(
                        Declaration) and statement.value.initial is not None and statement.value.initial.is_a(Scope):
                    yield from statement.check()
