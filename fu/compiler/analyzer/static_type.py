from logging import getLogger

from ...types import TypeBase, StaticType, ComposedType, GenericType, ARRAY_TYPE

from .. import CompilerNotice
from ..lexer import ArrayDef, GenericParamList, Identity, ParamList, Type_

from .scope import AnalyzerScope
from .static_variable_decl import StaticVariableDecl

_LOG = getLogger(__package__)


def type_from_lex(type_: Type_, scope: AnalyzerScope) -> TypeBase:
    """Construct a static type from a lexical type."""
    _LOG.debug(f"Constructing static type from `{type_}`.")
    existing = scope.in_scope(type_.ident.value)
    if existing is None:
        raise CompilerNotice('Error',
                             f"Type `{type_.ident.value}` has not been defined.",
                             location=type_.ident.location)
    assert not isinstance(existing, AnalyzerScope)
    assert isinstance(existing.type, TypeBase)
    actual_type = existing.type
    if isinstance(actual_type, StaticType):
        actual_type = actual_type.underlying
    if type_.mods:
        return _with_modifiers(actual_type, list(type_.mods), scope)
    return actual_type


def _with_modifiers(t: TypeBase, mods: list[ParamList | ArrayDef | GenericParamList], scope: AnalyzerScope) -> TypeBase:
    """Recursively apply modifiers."""
    assert isinstance(t, TypeBase), f"{t} was not `TypeBase`, instead {type(t).__name__}"
    ret: TypeBase | None = t
    _LOG.debug(f"Applying modifiers: {t.name} + {', '.join(repr(m) for m in mods)}")
    while mods:
        mod = mods.pop(0)
        match mod:
            case ArrayDef():
                ret = ARRAY_TYPE.resolve_generic({'T': ret})
            case ParamList():
                params = tuple(
                    type_from_lex(x.rhs if isinstance(x, Identity) else x, scope) for x in mod.params
                    if isinstance(x, Type_) or x.rhs != 'namespace')
                add = '(' + ', '.join(x.name for x in params) + ')'
                ret = ComposedType(ret.name + add, None, callable=(params, t))
            case GenericParamList():
                # assert isinstance(ret, )
                assert isinstance(ret, GenericType), f"Expected Generic Type, got {type(ret).__name__} `{ret.name}`"
                param_types: dict[str, TypeBase] = {}
                for i, (k, v) in enumerate(ret.generic_params.items()):
                    if i >= len(mod.params):
                        break
                    x = mod.params[i]
                    x_type = scope.in_scope(x.value)
                    _LOG.debug(f'Resolved generic template type {x.value} to {x_type}')
                    if isinstance(x_type, StaticVariableDecl):
                        x_decl = x_type
                        x_type = x_type.type
                    if x_type is None:
                        x_type = GenericType.GenericParam(x.value)
                    param_types[k] = x_type
                _LOG.debug(f"Replacing args in {t.name}: {','.join(f'{k}: {v.name}' for k,v in param_types.items())}")
                new_type = ret.resolve_generic(param_types)
                # assert not isinstance(new_type, GenericType) or all(not isinstance(x, GenericType)
                #                                                     for x in new_type.generic_params.values())
                _LOG.debug(f"got {new_type.name}")
                ret = new_type
            case _:
                raise NotImplementedError(f"Don't know how to apply modifier {mod}!")
    return ret

    # input(f"Done creating interface `{new_type.name}` ({type(new_type).__name__})!")
