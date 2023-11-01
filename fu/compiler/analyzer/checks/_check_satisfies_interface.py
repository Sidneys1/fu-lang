from ....types import InterfaceType, TypeBase
from ... import CompilerNotice
from ...lexer import CompilerNotice, SourceLocation


def _check_satisfies_interface(subject: TypeBase, interface: InterfaceType,
                               location: SourceLocation) -> CompilerNotice | None:
    from . import _expand_inherits
    inherits = list(_expand_inherits(subject))
    if interface in inherits:
        # fast path, this is checked in _check_type_declaration :)
        return None

    # check duck-typed?
    errs: list[CompilerNotice] = []

    for interface_member_name, interface_member_type in interface.members.items():
        checked = []
        haystack = [subject]
        subject_member_type = None
        while haystack:
            needle = haystack.pop()
            checked.append(needle)
            # input(f"Searching for {k} in {needle.name}")
            for inherits in needle.inherits:
                if inherits not in checked:
                    haystack.append(inherits)
            subject_member_type = subject.members.get(interface_member_name, None)
            if subject_member_type is not None:
                break

        if subject_member_type is None:
            if interface_member_name not in interface.default_impls:
                errs.append(CompilerNotice('Error', f"Missing `{interface.name}.{interface_member_name}`", location))
            continue

        if subject_member_type != interface_member_type:
            errs.append(
                CompilerNotice(
                    'Error',
                    f"`{subject.name}.{interface_member_name}` is a `{subject_member_type.name}`, while `{interface.name}.{interface_member_name}` is a `{interface_member_type.name}`.",
                    location))
    if not errs:
        return None
    return CompilerNotice('Error',
                          f"`{subject.name}` does not directly or indirectly implement interface `{interface.name}`.",
                          location,
                          extra=errs)
