from typing import Generator, Iterator, Any

from ....types import BOOL_TYPE, VOID_TYPE, EnumType, FloatType, GenericType, InterfaceType, IntType, TypeBase, ThisType, TypeType
from ... import CompilerNotice
from ...util import collect_returning_generator
from ...lexer import CompilerNotice, SourceLocation
from ..static_variable_decl import StaticVariableDecl
from ._check_satisfies_interface import _check_satisfies_interface


def _expand_generic_inherits(type_: GenericType) -> Iterator[GenericType]:
    to_expand: list[GenericType] = [type_]
    # already_expanded = []
    # print(f"Expanding inheritance of {type_.name}:")
    while to_expand:
        type_ = to_expand.pop()
        if isinstance(type_, ThisType) or isinstance(type_, TypeType):
            raise NotImplementedError(type_.name)
        # if type_ in already_expanded:
        #     continue
        yield type_
        # already_expanded.append(type_)
        for x in type_.generic_inheritance:
            # print(f"\t{type_.name} inherits {x.name}")
            to_expand.append(x)
    # input()


def _check_conversion(from_: TypeBase | StaticVariableDecl, to_: TypeBase | StaticVariableDecl,
                      location: SourceLocation) -> Generator[CompilerNotice, None, bool]:
    """
    Check implicit conversion compatiblity in converting `from_` to `to_`.
    Raises a `CompilerNotice` if there are warnings (e.g., narrowing) or errors (conversion not allowed).
    """
    from_decl = None
    if isinstance(from_, StaticVariableDecl):
        from_decl = from_
        from_ = from_.type
    to_decl = None
    if isinstance(to_, StaticVariableDecl):
        to_decl = to_
        to_ = to_.type

    if from_ == to_:
        return True

    if VOID_TYPE in (from_, to_):
        yield CompilerNotice('Error', "There are no conversions to or from void.", location=location)
        return False

    if from_ == BOOL_TYPE or to_ == BOOL_TYPE:
        raise NotImplementedError('Implicit bool conversions are not yet checked.')

    if isinstance(from_, EnumType) or isinstance(to_, EnumType):
        yield CompilerNotice('Error', "There are no implicit conversions of Enums.", location=location)
        return False

    match from_, to_:
    # case (TypeBase(size=None), _) | (_, TypeBase(size=None)):
    #     raise NotImplementedError(f"Can't compare types with unknown sizes ({from_.name} and/or {to_.name})...")
        case IntType(), IntType() if from_.size is not None and to_.size is not None:
            from_min, from_max = from_.range()
            to_min, to_max = to_.range()
            if (from_min < to_min) or (from_max > to_max):
                yield CompilerNotice(
                    'Warning',
                    f"Narrowing when implicitly converting from a `{from_.name}` ({from_.size*8}bit {'' if from_.signed else 'un'}signed) to a `{to_.name}` ({to_.size*8}bit {'' if to_.signed else 'un'}signed).",
                    location=location)
                return True
        case FloatType(), IntType():
            yield CompilerNotice('Warning',
                                 f"Loss of precision converting from a `{from_.name}` to a `{to_.name}`.",
                                 location=location)
            return True
        case FloatType(), FloatType():
            if to_.exp_bits < from_.exp_bits:
                raise CompilerNotice(
                    'Warning',
                    f"Loss of floating point precision converting from a `{from_.name}` to a `{to_.name}`.",
                    location=location)
        case _, GenericType.GenericParam():
            return True  # I hope!
        case _, _ if from_.callable is not None and to_.callable is not None:
            from_params, from_ret = from_.callable
            to_params, to_ret = to_.callable
            sub: list[CompilerNotice] = []

            allowed = True

            def allowed_from(g: Generator[CompilerNotice, None, bool]) -> Iterator[CompilerNotice]:
                nonlocal allowed
                try:
                    allowed |= yield from g
                except CompilerNotice as ex:
                    yield ex
                    allowed = False

            if len(from_params) != len(to_params):
                sub.append(CompilerNotice('Error', f"Mismatched parameters"))
            else:
                for from_param, to_param in zip(from_params, to_params):
                    sub.extend(allowed_from(_check_conversion(from_param, to_param, location)))

            if sub:
                yield CompilerNotice('Error', "Callable type mismatch:", location, extra=sub)
            return allowed
        case _, InterfaceType():
            # input(f"checking conversion between `{from_.name}` to interface `{to_.name}`")
            errs = _check_satisfies_interface(from_, to_, location)
            if errs is not None:
                yield errs
            return errs is None
        case GenericType(), GenericType():
            # if any(isinstance(x, InterfaceType) for x in to_.generic_params.values()):
            lhs_generic = list(_expand_generic_inherits(from_))
            rhs_generic = list(_expand_generic_inherits(to_))
            common: list[GenericType] = []
            for rhs in rhs_generic:
                if rhs in lhs_generic:
                    common.append(rhs)
            # print(
            #     f"{','.join(x.name for x in lhs_generic)}\n{','.join(x.name for x in rhs_generic)}\nCommon: {','.join(x.name for x in common)}"
            # )

            for common_generic in common:
                for param in common_generic.generic_params:
                    lhs_param = from_.generic_params[param]
                    rhs_param = to_.generic_params[param]
                    # print(
                    #     f"\tChecking generic param {param}: lhs<{param}={lhs_param.name}>, rhs<{param}={rhs_param.name}>"
                    # )
                    ret, errs = collect_returning_generator(_check_conversion(lhs_param, rhs_param, location))
                    if not ret:
                        yield from errs
                        return ret
            #         else:
            #             print('\t\tyep')
            # input()
            return True

            # yield CompilerNotice(
            #     'Critical', f"Don't know how to check conversion from generic `{from_.name}` to generic `{to_.name}`.",
            #     location)
            # return False
        case _, _:
            from . import _expand_inherits
            lhs_inherits = list(_expand_inherits(from_))
            rhs_inherits = list(_expand_inherits(to_))
            # input(f"{tuple(x.name for x in lhs_inherits)}/{tuple(x.name for x in rhs_inherits)}")

            common = []
            for rhs in rhs_inherits:
                if rhs in lhs_inherits:
                    common.append(rhs)

            if common:
                # input(
                #     f"Checked conversion between a `{(from_.resolved if isinstance(from_, ThisType) else from_).name}` (`{'`, `'.join(x.name for x in lhs_inherits)}`) to a `{to_.name}` resulted in `{'`, `'.join(x.name for x in common)}`"
                # )
                return True  # maybe??
            yield CompilerNotice('Error', f"Could not find a conversion between `{from_.name}` and `{to_.name}`.",
                                 location)
            return False
