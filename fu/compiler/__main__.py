import sys
from argparse import ArgumentParser, FileType
from io import SEEK_SET
from logging import getLogger, basicConfig, DEBUG, INFO, ERROR
from pathlib import Path
from typing import Iterator

from . import NAME, SourceLocation, CompilerNotice, SourceFile
from .analyzer.static_scope import _PARSING_BUILTINS
from .stream import StrStream, TokenStream
from .tokenizer import Token
from .lexer import parse, Document

_LOG = getLogger(__package__)


def load_file(path: Path) -> Document:
    with open(path, 'r', encoding='utf-8') as file:
        doc = parse(TokenStream([], generator=Token.token_generator(StrStream(file))))
        if doc is None:
            input(f'wtf error loading {path}')
        return doc


def load_std() -> Iterator[Document]:
    root = Path(__file__).parent.parent.parent / 'lib'
    path = root / '__builtins__.fu'
    SourceFile.set(str(path.relative_to(Path.cwd())))
    yield load_file(path)
    for path in root.glob('**/*.fu'):
        if path.name.startswith('.') or path.name == '__builtins__.fu':
            continue
        SourceFile.set(str(path.relative_to(Path.cwd())))
        yield load_file(path)


def main(*args) -> int:
    parser = ArgumentParser(NAME)
    parser.add_argument('-v', action='store_true')
    parser.add_argument('FILE', type=FileType())
    ns, unknown_args = parser.parse_known_args(args)

    if ns.v:
        basicConfig(level=DEBUG)
    else:
        getLogger(__package__ + ".lexer").setLevel(level=ERROR)
        basicConfig(level=INFO)

    docs: list[Document] = list(load_std())

    SourceFile.set(str(Path(ns.FILE.name).absolute().relative_to(Path.cwd())))
    str_stream = StrStream(ns.FILE)

    token_stream = TokenStream([], generator=Token.token_generator(str_stream))

    lex = parse(token_stream)

    # peeks, pops = str_stream.efficiency
    # print(f"Chars: {peeks=}, {pops=}, {pops/(pops+peeks or 1):0.2%}")
    # peeks, pops = token_stream.efficiency
    # print(f"Tokens: {peeks=}, {pops=}, {pops/(pops+peeks or 1):0.2%}")
    if not token_stream.eof:
        print(f"Failed at: {token_stream.peek()}")
        return 1
    if lex is None:
        print(f'Failed to lex.')
        return 1

    # for klass, calls in sorted(token_stream._who_called.items(), key=lambda t: t[1], reverse=True):
    #     print(klass.__name__, calls)

    # print('```\n' + str(lex) + '```')

    # lex.unrepr()

    # input()

    from .console import render_error

    from .analyzer import check_program
    docs.append(lex)
    errors = list(check_program(docs))

    if all(error.level.lower() not in ('error', 'critical') for error in errors):
        from .compile import compile
        bytecode = b''

        def _():
            nonlocal bytecode
            bytecode = yield from compile()

        errors.extend(_())

    files = set(error.location.file if error.location is not None else None for error in errors)
    errors_by_file = {
        file:
        sorted((error for error in errors if (None if error.location is None else error.location.file) == file),
               key=lambda y: y.location.lines[0] if y.location is not None else 0)
        for file in files
    }
    for file, errors in errors_by_file.items():
        if file is not None:
            length = (50 - len(file)) // 2
            print('-' * length, file, '-' * length)
        else:
            print('-' * 50)
        for error in errors:
            if file is None or error.location is None or error.level in ('Note', ):
                print(f"\033[92m{error.level:>7}: {error.message} \033[0m" +
                      (f"({error.location})" if error.location is not None else ''))
            else:
                render_error(error)
            if error != errors[-1]:
                print('\033[0;2m-----+\033[0m')

    if error_count := sum(1 if error.level.lower() in ('error', 'critical') else 0 for error in errors):
        return error_count

    from ..bytecode.vm import VM
    vm = VM(bytecode, unknown_args)
    try:
        vm.run()
    except VM.VmTerminated as ex:
        print(f'% VM terminated with {ex.exit_code}')
        return ex.exit_code
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
