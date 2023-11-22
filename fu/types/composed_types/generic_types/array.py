"""The built-in Array generic type."""

from ...integral_types import SIZE_TYPE, USIZE_TYPE
from . import GenericType

ARRAY_GENERIC_PARAM = GenericType.GenericParam('T')  # pylint: disable=too-many-function-args
ARRAY_TYPE = GenericType('Array',
                         size=None,
                         reference_type=True,
                         indexable=((SIZE_TYPE, ), ARRAY_GENERIC_PARAM),
                         instance_members={'length': USIZE_TYPE},
                         static_members={},
                         readonly={'length'},
                         generic_params={'T': ARRAY_GENERIC_PARAM},
                         is_builtin=True)

__all__ = ('ARRAY_GENERIC_PARAM', 'ARRAY_TYPE')
