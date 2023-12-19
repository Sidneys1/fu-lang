from dataclasses import dataclass, field, replace, InitVar
from logging import getLogger
from typing import Self, Union, ClassVar, cast, Literal

from ....compiler import CompilerNotice, SourceLocation
from ....compiler.tokenizer import SpecialOperatorType
from ... import TypeBase
from .. import ComposedType, ThisType, CallSignature, StaticType

_LOG = getLogger(__package__)


def _is_generic_of(t: 'GenericType', p: 'GenericType.GenericParam') -> bool:
    """Determine if a given `GenericType` is generic on a given `GenericParam`."""
    # _LOG.debug(f"Checking if {t.name} is generic of {p.name}")
    for tp in t.generic_params.values():
        match tp:
            case GenericType():
                if _is_generic_of(tp, p):
                    return True
            case GenericType.GenericParam():
                if tp is p:
                    return True
            case _:
                raise NotImplementedError(
                    f"Don't know how to check whether {type(tp).__name__} is generic on `{p.name}`.")
    return False


def _rebuild_generic_type(t: 'GenericType',
                          new: dict[str, TypeBase],
                          location: SourceLocation | None = None) -> Union[ComposedType, 'GenericType']:
    """Rebuild a generic type, given resolution of some or all of the generic parameters."""
    # input(f"Building generic type! Base: {t.name} with new params {new}")
    inherits: list[TypeBase] = []
    indexable: CallSignature | None = None
    callable_: CallSignature | None = None
    instance_members: dict[str, TypeBase] = {}
    static_members: dict[str, TypeBase] = {}
    special_operators: dict[SpecialOperatorType, CallSignature] = {}
    generic_inheritance: list[GenericType] = list(t.generic_inheritance)

    all_generics = {**t.generic_params}
    all_generics.update(new)
    still_generics = {k: v for k, v in all_generics.items() if isinstance(v, GenericType.GenericParam)}
    # from ... import ThisType
    new_this = ThisType()
    new_static = StaticType()

    updated_generics: dict[str, TypeBase] = {}
    """Generics (resolved or not) being replaced *this round*."""

    not_updated_generics: dict[str, TypeBase] = {}
    """Generics (resolved or not) not being replaced *this round*."""

    for nk, nv in new.items():
        if nv is t.generic_params[nk]:
            not_updated_generics[nk] = t.generic_params[nk]
            continue
        updated_generics[nk] = nv

    if updated_generics and t not in generic_inheritance:
        # input(f"Adding {t.name} to generic inheritance!")
        generic_inheritance.append(t)
    # else:
    #     input(f"NOT adding {t.name} to generic inheritance ({bool(updated_generics)=} and {t not in generic_inheritance=})!")

    # Make sure we're
    if not_generic := [g for g in updated_generics if not isinstance(t.generic_params[g], GenericType.GenericParam)]:
        raise CompilerNotice('Error', f"Generic parameter(s) `{'`, `'.join(not_generic)}` have already been resolved!",
                             location)

    # still_generic = bool(still_generics)

    def _quick_generic(_t: TypeBase) -> TypeBase:
        match _t:
            case GenericType.GenericParam() if _t not in not_updated_generics.values():
                return next((updated_generics[k] for k, v in t.generic_params.items()
                             if isinstance(v, GenericType.GenericParam) and k in updated_generics and v is _t), _t)
            case GenericType():
                # print(f'Found generic nested type: {_t.name}')
                to_update: dict[str, TypeBase] = {}
                for gk, gv in _t.generic_params.items():
                    if not isinstance(gv, GenericType.GenericParam):
                        # print(f"\tSkipping {gk}, it's already no longer generic")
                        continue
                    # gk is still generic. Does it map to one of our params?
                    tk = None
                    # print(f"\tChecking if it maps to us ({updated_generics.keys()})...")
                    for ok, ov in t.generic_params.items():
                        if ok not in updated_generics:
                            # print(f"\t\tSkipping {ok}, it hasn't been updated...")
                            continue
                        if ov is gv:
                            tk = ok
                            # print(f"\t\tAha, {gk} maps to {ok}")
                            break
                        # print(f"\t\tSkipping {ok}, it hasn't been updated...")
                    if tk is None:
                        # print(f"{gk} does not seem to map into our current generic...")
                        continue
                    to_update[gk] = updated_generics[tk]
                # to_update = {t.reverse_lookup(v) for uk, uv in updated_generics.items() if isinstance(v, GenericType.GenericParam) and _t.is_generic_of(v)}
                if not to_update:
                    return _t
                # input(f"Updating generics in {_t.name}: {', '.join(f'{k}={v.name}' for k, v in to_update.items())}")
                return _t.resolve_generic(to_update)
            case ComposedType() if type(_t) == ComposedType and _t.callable is not None:
                # Bland callable type
                assert not _t.instance_members and _t.indexable is None and _t.inherits is None
                params, ret = _t.callable
                params = tuple(_quick_generic(p) for p in params)
                ret = _quick_generic(ret)
                new_name = f"{ret.name}({', '.join(x.name for x in params)})"
                return replace(_t, name=new_name, callable=(params, ret))
            case ComposedType() if type(_t) == ComposedType and _t.indexable is not None:
                # Bland indexable type
                assert not _t.instance_members and _t.callable is None and _t.inherits is None
                params, ret = _t.indexable
                params = tuple(_quick_generic(p) for p in params)
                ret = _quick_generic(ret)
                new_name = f"{ret.name}[{', '.join(x.name for x in params)}]"
                return replace(_t, name=new_name, indexable=(params, ret))
            case ThisType() if _t.resolved == t:
                # input(f"Oops, this type: {_t.name}")
                return new_this
            case ThisType(resolved=GenericType()) if _t.resolved not in not_updated_generics.values():
                ret = ThisType()  # type: ignore[call-arg]
                assert _t.resolved is not None
                resolved = _quick_generic(_t.resolved)
                assert isinstance(resolved, ComposedType)
                ret.resolve(resolved)
                return ret
            case ThisType(resolved=TypeBase()):
                nf = ', '.join(f"{k}={v.name}" for k, v in new.items())
                raise NotImplementedError(
                    f"Don't know how to resolve other this?? For {_t.name} when converting {t.name} with {nf}")
            case ThisType():
                raise NotImplementedError("Don't know how to resolve unbound this??")
            case _:
                # _LOG.debug(f"Don't know how to resolve generic of {_t.name} ({type(_t).__name__}/{type(_t).__bases__})!")
                return _t
        raise NotImplementedError()

    # 2. Inherits
    if t.inherits is not None:
        for i in t.inherits:
            new_i = _quick_generic(i)
            # input(f"In generic resolution: {t.name} inherits {i.name}, which is now {new_i.name}")
            if new_i not in inherits:
                inherits.append(new_i)

    # 3. Indexable
    if t.indexable is not None:
        indexable = tuple(_quick_generic(p) for p in t.indexable[0]), _quick_generic(t.indexable[1])

    # 4. Callable
    if t.callable is not None:
        callable_ = tuple(_quick_generic(p) for p in t.callable[0]), _quick_generic(t.callable[1])

    # 5. Instance Members
    for k, v in t.instance_members.items():
        instance_members[k] = _quick_generic(v)
        # input(f"Replacing {k}={v.name} with {members[k].name}")

    # 6. Static Members
    for k, v in t.static_members.items():
        static_members[k] = _quick_generic(v)
        # input(f"Replacing {k}={v.name} with {members[k].name}")

    # 7. Special Operators
    for sk, sv in t.special_operators.items():
        special_operators[sk] = tuple(_quick_generic(p) for p in sv[0]), _quick_generic(sv[1])
        # input(f"Resolving special operator {sk.name} for {t.name} from `{sv[1].name}({', '.join(x.name for x in sv[0])})` to `{special_operators[sk][1].name}({',  '.join(x.name for x in special_operators[sk][0])})`")

    all_params = dict(t.generic_params)
    all_params.update(updated_generics)

    # if t not in inherits and any(not isinstance(g, GenericType.GenericParam) for g in updated_generics.values()):
    # input(f"Inserting supertype because {tuple(x for x in updated_generics if not isinstance(x, GenericType.GenericParam))}")
    # inherits.insert(0, t)

    # if still_generic:

    if not still_generics:
        # TODO: calculate size
        pass

    kwargs: dict = dict(
        name=t.real_name,  # pylint: disable=protected-access
        # size=None,
        inherits=tuple(inherits),
        indexable=indexable,
        # reference_type=t.reference_type,
        callable=callable_,
        instance_members=instance_members,
        static_members=static_members,
        readonly=t.readonly,
        special_operators=special_operators,
        generic_params=all_params,
        generic_inheritance=tuple(generic_inheritance),
        static_type=new_static,
        this_type=new_this)

    # from .type_ import StaticType
    # if isinstance(t, StaticType):
    #     # These are computed values for TypeTypes...
    #     del kwargs['name']
    #     # del kwargs['size']
    #     # del kwargs['inherits']
    #     # del kwargs['indexable']
    #     # del kwargs['callable']
    #     # del kwargs['reference_type']
    #     # del kwargs['instance_members']
    #     # del kwargs['static_members']
    #     # del kwargs['readonly']

    _LOG.debug('1')
    ret = type(t)(**kwargs)
    _LOG.debug('2')
    new_this.resolve(ret)
    new_static.resolve(ret, ret.static_members)
    mode = f'still-generic-on-`{"`-`".join(still_generics)}`' if still_generics else 'fully-resolved'
    nf = '`, `'.join(f'{k}->{v.name}' for k, v in new.items())
    _LOG.debug(f"Resolution of `{nf}` for {t.name} produced {mode} `{ret.name}`.")
    return ret


@dataclass(frozen=True, kw_only=True, slots=True, eq=False)
class GenericType(ComposedType):
    """Represents a type with unresolved generic parameters."""

    @dataclass(frozen=True, kw_only=True, slots=True, eq=False)
    class GenericParam(TypeBase):
        """A generic unresolved parameter type."""
        is_builtin: ClassVar[bool] = field(init=False, default=False)  # type: ignore[misc]

        def get_size(self) -> int | None:
            return None

        def intrinsic_size(self) -> int | None:
            return None

        def __eq__(self, __value: object) -> bool:
            return isinstance(__value, GenericType.GenericParam)

    real_name: str = field(init=False)
    generic_params: dict[str, TypeBase]
    generic_inheritance: tuple['GenericType', ...] = ()

    def is_still_generic(self) -> bool:
        return any(isinstance(x, GenericType.GenericParam) for x in self.generic_params.values())

    def get_size(self) -> int | None:
        if self.is_still_generic():
            return None
        return ComposedType.get_size(self)

    def __post_init__(self):
        ComposedType.__post_init__(self)

        real_name = getattr(self, 'real_name', None)
        _LOG.debug(
            f"Creating generic, {self.name=}, {real_name=}, <{', '.join(k + '=' + v.name for k, v in self.generic_params.items())}>"
        )

        if real_name is None:
            # Save the "actual" name.
            object.__setattr__(self, 'real_name', self.name)
            real_name = self.name

        if self.generic_params:
            names = ','.join(v.name if k == v.name or not isinstance(v, GenericType.GenericParam) else f"{k}={v.name}"
                             for k, v in self.generic_params.items())
            object.__setattr__(self, 'name', f"{real_name}<{names}>")

        _LOG.debug(f"Done creating generic: {self.name=}, {real_name=}")

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, GenericType):
            return False

        # Ignore self.name in favor of self.real_name
        ours = (self.real_name, self.inherits, self.indexable, self.callable, self.instance_members,
                self.static_members, self.readonly, self.special_operators)
        theirs = (self.real_name, self.inherits, self.indexable, self.callable, self.instance_members,
                  self.static_members, self.readonly, self.special_operators)

        if ours != theirs:
            return False

        return self.generic_params == __value.generic_params

    def resolve_generic(self, params: dict[str, TypeBase] | None = None, **kwargs: TypeBase) -> Self:
        if params is None:
            params = {}
        else:
            params = dict(params)  # copy to make sure we're not modifying the original
        params.update(kwargs)
        assert params, f"Get resolve_generic_instance with nothing! ({params!r})"
        return cast(Self, _rebuild_generic_type(self, params))

    def is_generic_of(self, t: GenericParam) -> bool:
        return _is_generic_of(self, t)

    def reverse_lookup(self, t: GenericParam) -> str:
        for k, v in self.generic_params.items():
            if t is v:
                return k
        raise ValueError(f"Could not find `{t.name}` in `{self.name}`")


@dataclass(frozen=True, kw_only=True, slots=True)
class InterfaceType(GenericType):
    default_impls: set[str] = field(default_factory=set)


__all__ = ('GenericType', 'InterfaceType')
