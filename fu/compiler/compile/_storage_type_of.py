from ...virtual_machine.bytecode.structures import SourceLocation

from .. import CompilerNotice
from ..analyzer.scope import AnalyzerScope, StaticVariableDecl

from .scope import FunctionScope
from .storage import Storage, StorageDescriptor


def storage_type_of(name: str, loc: SourceLocation) -> StorageDescriptor:
    current_fn = FunctionScope.current_fn()
    if current_fn is None:
        raise NotImplementedError()
    for i, (k, v) in enumerate(current_fn.args.items()):
        if k == name:
            return StorageDescriptor(Storage.Arguments, v, slot=i)
    for i, (k, v) in enumerate(current_fn.locals.items()):
        if k == name:
            return StorageDescriptor(Storage.Locals, v, slot=i)
    for k, v in current_fn.decls.items():
        if k == name:
            return StorageDescriptor(Storage.Locals, v, slot=None)

    res = current_fn.static_scope.in_scope(name)
    if res is None:
        raise CompilerNotice('Error', f"Cannot find `{name}` (in `{current_fn.fqdn}`).", loc)

    if isinstance(res, AnalyzerScope):
        return StorageDescriptor(Storage.Static, res)
    if isinstance(res, StaticVariableDecl):
        return StorageDescriptor(Storage.Static, res.type, decl=res)

    raise CompilerNotice('Error', f"Cannot find `{name}` (in `{current_fn.fqdn}`).", loc)
