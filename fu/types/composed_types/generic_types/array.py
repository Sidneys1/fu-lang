from ...integral_types import USIZE_TYPE, SIZE_TYPE

from . import GenericType

ARRAY_GENERIC_PARAM = GenericType.GenericParam('T')
ARRAY_TYPE = GenericType('Array',
                         size=None,
                         reference_type=True,
                         indexable=((SIZE_TYPE, ), ARRAY_GENERIC_PARAM),
                         members={'length': USIZE_TYPE},
                         readonly={'length'},
                         generic_params={'T': ARRAY_GENERIC_PARAM})

__all__ = ('ARRAY_GENERIC_PARAM', 'ARRAY_TYPE')
