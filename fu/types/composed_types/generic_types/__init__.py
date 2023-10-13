from dataclasses import dataclass, field
from typing import Self, Union
from logging import getLogger

from ....compiler.tokenizer import SpecialOperatorType

from ... import TypeBase

from .. import ComposedType

_LOG = getLogger(__package__)

def _is_generic_of(t: 'GenericType', p: 'GenericType.GenericParam') -> bool:
    for tp in t.generic_params.values():
        match tp:
            case GenericType():
                if _is_generic_of(tp, p):
                    return True
            case GenericType.GenericParam():
                if p == t:
                    return True
            case _:
                raise NotImplementedError(
                    f"Don't know how to check whether {type(tp).__name__} is generic on `{p.name}`.")
    return False


def _rebuild_generic_type(t: 'GenericType',
                          new: dict[str, TypeBase],
                          preserve_inheritance: bool = False) -> Union[ComposedType, 'GenericType']:
    inherits: tuple[TypeBase, ...] | None = None
    indexable: tuple[tuple[TypeBase, ...], TypeBase] | None = None
    callable: tuple[tuple[TypeBase, ...], TypeBase] | None = None
    members: dict[str, TypeBase] = {}
    special_operators: dict[SpecialOperatorType, tuple[tuple[TypeBase, ...], TypeBase]] = {}

    updated_generics: dict[str, TypeBase] = {}
    not_updated_generics: dict[str, TypeBase] = {}
    for nk, nv in new.items():
        if nv == t.generic_params[nk]:
            not_updated_generics[nk] = t.generic_params[nk]
            continue
        updated_generics[nk] = nv

    still_generic = bool(not_updated_generics)

    def _quick_generic(_t: TypeBase) -> TypeBase:
        if isinstance(_t, GenericType.GenericParam) and _t not in not_updated_generics.values():
            _t = next((updated_generics[k] for k, v in t.generic_params.items()
                       if isinstance(v, GenericType.GenericParam) and k in updated_generics and v == _t), _t)
        elif isinstance(_t, GenericType) and any(
                _t.is_generic_of(v)
                for k, v in t.generic_params if k in updated_generics and isinstance(v, GenericType.GenericParam)):
            _t = _t.resolve_generic_instance(updated_generics)
        return _t

    # 2. Inherits
    if t.inherits is not None:
        inherits = tuple(_quick_generic(i) for i in t.inherits)

    # 3. Indexable
    if t.indexable is not None:
        indexable = tuple(_quick_generic(p) for p in t.indexable[0]), _quick_generic(t.indexable[1])

    # 4. Callable
    if t.callable is not None:
        callable = tuple(_quick_generic(p) for p in t.callable[0]), _quick_generic(t.callable[1])

    # 5. Members
    for k, v in t.members.items():
        members[k] = _quick_generic(v)

    # 5. Special Operators
    for sk, sv in t.special_operators.items():
        special_operators[sk] = tuple(_quick_generic(p) for p in sv[0]), _quick_generic(sv[1])

    all_params = dict(t.generic_params)
    all_params.update(updated_generics)
    if inherits is None or t not in inherits:
        inherits = (t, *inherits) if inherits is not None else  (t, )

    if still_generic or preserve_inheritance:
        from .type_ import TypeType
        kwargs: dict = dict(size=None, inherits=inherits, indexable=indexable,
                           reference_type=t.reference_type,
                           callable=callable,
                           members=members,
                           readonly=t.readonly,
                           special_operators=special_operators,
                           generic_params=all_params)
        if isinstance(t, TypeType):
            del kwargs['size']
            del kwargs['inherits']
            del kwargs['indexable']
            del kwargs['callable']
        ret = type(t)(t._name, **kwargs)
        mode = f'still-generic-on `{'`, `'.join(not_updated_generics)}`' if still_generic else 'fully-resolved'
        if preserve_inheritance:
            mode += f' (but preserving inheritance from {type(t).__name__})'
        _LOG.debug(
            f"Resolution of `{'`, `'.join(new)}` for {t.name} produced {mode} `{ret.name}`."
        )
        return ret
    from .array import ARRAY_TYPE
    if t == ARRAY_TYPE:
        name = all_params['T'].name + '[]'
    else:
        name = f"{t._name}<{', '.join(k.name for k in all_params.values())}>"
    _LOG.debug(f"Resolution of `{'`, `'.join(new)}` for {t.name} produced fully-resolved `{name}`.")
    return ComposedType(name,
                        size=None,
                        reference_type=t.reference_type,
                        inherits=inherits,
                        indexable=indexable,
                        callable=callable,
                        members=members,
                        readonly=t.readonly,
                        special_operators=special_operators)


@dataclass(frozen=True, kw_only=True, slots=True)
class GenericType(ComposedType):
    """Represents a type with unresolved generic parameters."""

    @dataclass(frozen=True, kw_only=True, slots=True, eq=False)
    class GenericParam(TypeBase):
        """A generic unresolved parameter type."""
        size: None = field(init=False, default=None)

    _name: str = field(init=False)
    generic_params: dict[str, TypeBase]

    def __post_init__(self):
        names = ','.join(v.name for v in self.generic_params.values())
        object.__setattr__(self, '_name', self.name)
        object.__setattr__(self, 'name', f"{self.name}<{names}>")

    def resolve_generic_instance(self,
                                 params: dict[str, TypeBase] | None = None,
                                 preserve_inheritance: bool = False,
                                 **kwargs: TypeBase) -> Self | ComposedType:
        if params is None:
            params = {}
        else:
            params = dict(params)  # copy to make sure we're not modifying the original
        params.update(kwargs)
        assert params
        return _rebuild_generic_type(self, params, preserve_inheritance=preserve_inheritance)

    def is_generic_of(self, t: GenericParam) -> bool:
        return _is_generic_of(self, t)

__all__ = ('GenericType', )
