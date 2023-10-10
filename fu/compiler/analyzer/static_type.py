from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from logging import getLogger

from .. import CompilerNotice
from ..typing import TypeBase, TypeType
from ..typing.composed_types.generic_types import GenericType
from ..typing.composed_types.generic_types.array import ARRAY_TYPE
from ..lexer import Type_, ParamList, ArrayDef, Identity, GenericParamList

from .static_variable_decl import StaticVariableDecl

if TYPE_CHECKING:
    from . import StaticScope

_LOG = getLogger(__package__)


def type_from_lex(type: Type_, scope: 'StaticScope') -> TypeBase:
    """Construct a static type from a lexical type."""
    _LOG.debug(f"Constructing static type from `{type}`.")
    existing = scope.in_scope(type.ident.value)
    if existing is None:
        raise CompilerNotice('Error', f"Type `{type.ident.value}` has not been defined.", location=type.ident.location)
    assert isinstance(existing.type, TypeBase)
    actual_type = existing.type
    if isinstance(actual_type, TypeType):
        actual_type = actual_type.underlying
    if type.mods:
        return _with_modifiers(actual_type, list(type.mods), scope)
    return actual_type


def _with_modifiers(t: TypeBase, mods: list[ParamList | ArrayDef | GenericParamList], scope: 'StaticScope') -> TypeBase:
    """Recursively apply modifiers."""
    assert isinstance(t, TypeBase), f"{t} was not `TypeBase`, instead {type(t).__name__}"
    ret: TypeBase | None = t
    while mods:
        mod = mods.pop(0)
        match mod:
            case ArrayDef():
                ret = ARRAY_TYPE.resolve_generic_instance({'T': ret})
            case ParamList():
                params = tuple(
                    type_from_lex(x.rhs if isinstance(x, Identity) else x, scope) for x in mod.params
                    if isinstance(x, Type_) or x.rhs != 'namespace')
                add = '(' + ', '.join(x.name for x in params) + ')'
                ret = TypeBase(ret.name + add, size=None, callable=(params, t))
            case GenericParamList():
                # assert isinstance(ret, )
                assert isinstance(ret, GenericType), f"Expected Generic Type, got {type(ret).__name__} `{ret.name}`"
                param_types: dict[str, TypeBase] = {}
                for i, (k, v) in enumerate(ret.generic_params.items()):
                    if i >= len(mod.params):
                        break
                    x = mod.params[i]
                    x_type = scope.in_scope(x.value)
                    if isinstance(x_type, StaticVariableDecl):
                        x_decl = x_type
                        x_type = x_type.type
                    if x_type is None:
                        x_type = GenericType.GenericParam(x.value)
                    param_types[k] = x_type
                new_type = ret.resolve_generic_instance(param_types)
                assert not isinstance(new_type, GenericType) or all(not isinstance(x, GenericType)
                                                                    for x in new_type.generic_params.values())
                ret = new_type
            case _:
                raise NotImplementedError(f"Don't know how to apply modifier {mod}!")
    return ret
