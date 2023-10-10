from typing import Self, TYPE_CHECKING
from dataclasses import dataclass, field

from .. import CompilerNotice
from ..lexer import Type_, ParamList, ArrayDef, Identity

if TYPE_CHECKING:
    from ..analyzer import StaticScope


@dataclass(frozen=True, slots=True, kw_only=True)
class StaticType:
    """Describes a Type that was resolvable at static analysis time."""

    name: str = field(kw_only=False)
    members: dict[str, Self] = field(default_factory=dict)

    @classmethod
    def from_type(cls, type: Type_, scope: 'StaticScope') -> Self:
        """
        Construct a static type from a lexical type definition.

        Example: int(a: str[])
        resolve_type = Identifier<int>
        mods = ParamList<Identity|Type_, ...> | ArrayDef
        """

        resolve_type = scope.in_scope(type.ident.value)
        if resolve_type is None:
            raise CompilerNotice('Error', f"`{type.ident.value}` is undefined.", type.ident.location)
        if not type.mods:
            # No composition (callable, arrays, etc).
            return resolve_type.type
        # Ok, we need to construct a composed type...
        return cls._from_type_recursive(resolve_type.type, list(type.mods), scope)

    @classmethod
    def _from_type_recursive(cls, type: Self, mods: list[ParamList | ArrayDef], scope: 'StaticScope') -> Self:
        assert isinstance(type, StaticType)
        ret: Self | None = type
        while mods:
            mod = mods.pop(0)
            match mod:
                case ArrayDef():
                    # from . import ARRAY_MEMBERS
                    # add = "[]" if mod.size is None else f"[{mod.size.value}]"
                    # TODO: support non-integer array subscripting
                    ret = ArrayType(ret.name + '[]', return_type=ret)
                    # ret = cls(ret.name + add,
                    #           evals_to=ret,
                    #           members=ARRAY_MEMBERS,
                    #           array=True if mod.size is None else int(mod.size.value))
                case ParamList():
                    params = tuple(
                        cls.from_type(x.rhs if isinstance(x, Identity) else x, scope) for x in mod.params
                        if isinstance(x, Type_) or x.rhs != 'namespace')
                    add = '(' + ', '.join(x.name for x in params) + ')'
                    ret = CallableType(ret.name + add, return_type=ret, params=params)
                    # ret = cls(ret.name + add, evals_to=ret, callable=params)
                case _:
                    raise NotImplementedError()
        return ret


@dataclass(frozen=True, slots=True, kw_only=True)
class CallableType(StaticType):
    """Describes a Type that is a function."""
    params: tuple[Self, ...]
    return_type: StaticType


# @dataclass(frozen=True, slots=True, kw_only=True)
# class CallableOverload(StaticType):
#     """Describes a Type that can resolve to one of many callable signatures."""
#     callables: list[CallableType]


def _array_type_default_factory():
    from . import INT_TYPE
    return (INT_TYPE, )


def _array_members_default_factory() -> dict[str, StaticType]:
    from . import INT_TYPE
    return {'length': INT_TYPE}


@dataclass(frozen=True, slots=True, kw_only=True)
class ArrayType(StaticType):
    """Describes a Type that is a basic array (not just any old subscriptable)."""

    array: tuple[Self, ...] = field(default_factory=_array_type_default_factory)
    return_type: StaticType
    members: dict[str, StaticType] = field(default_factory=_array_members_default_factory)
