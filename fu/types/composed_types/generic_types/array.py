"""The built-in Array generic type."""

from collections import OrderedDict

from ...integral_types import SIZE_TYPE, USIZE_TYPE
from ..static_type import StaticType
from . import GenericType, ThisType

ARRAY_GENERIC_PARAM = GenericType.GenericParam('T')  # pylint: disable=too-many-function-args
ARRAY_STATIC = StaticType()
ARRAY_TYPE = GenericType(
    'Array',
    #  reference_type=True,
    indexable=((SIZE_TYPE, ), ARRAY_GENERIC_PARAM),
    instance_members={'length': USIZE_TYPE},
    static_members={},
    readonly={'length'},
    generic_params={'T': ARRAY_GENERIC_PARAM},
    is_builtin=True,
    this_type=ThisType(),
    static_type=ARRAY_STATIC)
ARRAY_STATIC.resolve(ARRAY_TYPE, OrderedDict())

__all__ = ('ARRAY_GENERIC_PARAM', 'ARRAY_TYPE')
