import sys
from os import sep as pathsep
from argparse import ArgumentParser, ArgumentError
from logging import getLogger, basicConfig, DEBUG, INFO, ERROR
from pathlib import Path
from typing import Protocol

from fu.compiler.discovery import DEFAULT_STD_ROOT

from . import NAME
from .discovery import load_std, discover_files
from .lexer import Document

_LOG = getLogger(__package__)


class ParsedArgs(Protocol):
    run: bool
    verbose: bool
    # FILE: FileType
    root: Path
    std_root: Path

    @staticmethod
    def root_path(string: str) -> Path:
        ret = Path(string).absolute()
        if not ret.is_dir():
            raise ArgumentError(None, f"`{ret}` is not a directory.")
        cwd = Path.cwd()
        if cwd != ret and cwd not in ret.parents:
            raise ArgumentError(None, f"`{ret}` is not a subdirectory of `{cwd}`.")
        return ret.absolute().relative_to(cwd)

    @staticmethod
    def std_root_path(string: str) -> Path:
        ret = Path(string)
        if not ret.is_dir():
            raise ArgumentError(None, f"`{ret}` is not a directory.")
        if not (ret / '__builtins__.fu').is_file():
            raise ArgumentError(None, f"`{ret}` does not contain `__builtins__.fu`.")
        return ret.absolute()


def main(*args) -> int:
    parser = ArgumentParser(NAME)
    parser.add_argument('-r', '--run', help="Compile and run.", action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--std-root', type=ParsedArgs.std_root_path, default=DEFAULT_STD_ROOT)
    parser.add_argument('root',
                        metavar='DIR',
                        nargs='?',
                        type=ParsedArgs.root_path,
                        help='Compile source files found under this directory (default: %(default)s).',
                        default='.' + pathsep)
    ns: ParsedArgs
    ns, unknown_args = parser.parse_known_args(args)

    if ns.verbose:
        basicConfig(level=DEBUG)
    else:
        getLogger(__package__ + ".lexer").setLevel(level=ERROR)
        basicConfig(level=INFO)

    docs: list[Document] = list(load_std(ns.std_root))
    docs.extend(discover_files(ns.root))
    # SourceFile.set(str(ns.root))

    # str_stream = StrStream(ns.FILE)

    # token_stream = TokenStream([], generator=Token.token_generator(str_stream))

    # lex = parse(token_stream)

    # peeks, pops = str_stream.efficiency
    # print(f"Chars: {peeks=}, {pops=}, {pops/(pops+peeks or 1):0.2%}")
    # peeks, pops = token_stream.efficiency
    # print(f"Tokens: {peeks=}, {pops=}, {pops/(pops+peeks or 1):0.2%}")
    # if not token_stream.eof:
    #     print(f"Failed at: {token_stream.peek()}")
    #     return 1
    # if lex is None:
    #     print(f'Failed to lex.')
    #     return 1

    # for klass, calls in sorted(token_stream._who_called.items(), key=lambda t: t[1], reverse=True):
    #     print(klass.__name__, calls)

    # print('```\n' + str(lex) + '```')

    # lex.unrepr()

    # input()

    from .console import render_error

    from .analyzer import check_program
    # docs.append(lex)
    errors = list(check_program(docs))

    if all(error.level.lower() not in ('error', 'critical') for error in errors):
        from .compile import compile
        binary = None

        def _():
            nonlocal binary
            binary = yield from compile()

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

    if ns.run:
        if binary is None:
            return -1

        from ..virtual_machine import VM
        vm = VM(binary, unknown_args)
        try:
            vm.run()
        except VM.VmTerminated as ex:
            print(f'% VM terminated with {ex.exit_code}')
            return ex.exit_code

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
