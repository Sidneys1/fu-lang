from .. import SourceLocation, MODULE_LOGGER

_LOG = MODULE_LOGGER.getChild(__name__)

from .static_type import StaticType
from .compile_time_surrogate import CompileTimeSurrogate

STATIC_SPACE_LOCATION = SourceLocation((0, 0), (0, 0), (0, 0), '<static>')
BOOL_TYPE = StaticType('bool', defined_at=STATIC_SPACE_LOCATION)
STR_TYPE = StaticType('str', defined_at=STATIC_SPACE_LOCATION)
INT_TYPE = StaticType('int', defined_at=STATIC_SPACE_LOCATION)
TYPE_TYPE = CompileTimeSurrogate('type', defined_at=STATIC_SPACE_LOCATION)
VOID_TYPE = StaticType('void', defined_at=STATIC_SPACE_LOCATION)

TYPE_TYPE.members['has'] = CompileTimeSurrogate('type.has',
                                                defined_at=STATIC_SPACE_LOCATION,
                                                evals_to=BOOL_TYPE,
                                                callable=(TYPE_TYPE, STR_TYPE))

STR_ARRAY_TYPE = StaticType('str[]', defined_at=STATIC_SPACE_LOCATION, evals_to=STR_TYPE, array=True)
ENTRYPOINT_TYPE = StaticType('int(str[])',
                             defined_at=STATIC_SPACE_LOCATION,
                             evals_to=INT_TYPE,
                             callable=(STR_ARRAY_TYPE, ))
ENTRYPOINT_METADATA_TYPE = CompileTimeSurrogate('Entrypoint',
                                                defined_at=STATIC_SPACE_LOCATION,
                                                evals_to=VOID_TYPE,
                                                callable=(ENTRYPOINT_TYPE, ))

BUILTINS: dict[str, StaticType] = {
    'void': VOID_TYPE,
    'int': INT_TYPE,
    'type': TYPE_TYPE,
    'bool': BOOL_TYPE,
    'str': STR_TYPE,
    'assert': StaticType('assert',
                         callable=(BOOL_TYPE, ),
                         defined_at=SourceLocation((0, 0), (0, 0), (0, 0), '<static>')),
    'Entrypoint': ENTRYPOINT_METADATA_TYPE,
}
