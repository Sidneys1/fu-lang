import sys
from argparse import ArgumentError, ArgumentParser
from logging import DEBUG, ERROR, INFO, basicConfig, getLogger
from os import sep as pathsep
from pathlib import Path
from typing import Protocol

from . import NAME
from .analyzer import check_program
from .analyzer.scope import AnalyzerScope, set_global_scope
from .console import render_error
from .discovery import DEFAULT_STD_ROOT, discover_files, load_std, parse_file
from .lexer import Document

_LOG = getLogger(__package__)


class ParsedArgs(Protocol):
    run: bool
    verbose: bool
    check_only: bool
    format: bool
    input: Path
    std: Path
    args: list[str]

    @staticmethod
    def parse_input_path(string: str) -> Path:
        ret = Path(string).absolute()
        cwd = Path.cwd()
        if cwd != ret and cwd not in ret.parents:
            raise ArgumentError(None, f"`{ret}` is not a subdirectory of current working directory `{cwd}`.")
        return ret

    @staticmethod
    def parse_std_path(string: str) -> Path:
        ret = Path(string).absolute()
        if not ret.is_dir():
            raise ArgumentError(None, f"`{ret}` is not a directory.")
        if not (ret / '__builtins__.fu').is_file():
            raise ArgumentError(None, f"`{ret}` does not contain `__builtins__.fu`.")
        return ret


def main(*args) -> int:
    parser = ArgumentParser(NAME)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--check-only', help="Stop after checking.", action='store_true')
    group.add_argument('-r', '--run', help="Compile and run.", action='store_true')
    group.add_argument('-f', '--format', help="Print a formatted version of the input file.", action='store_true')

    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--std',
                        metavar='STD_PATH',
                        type=ParsedArgs.parse_std_path,
                        help="Path to the standard library (default: `%(default)s`).",
                        default=DEFAULT_STD_ROOT)
    parser.add_argument(
        'input',
        metavar='PATH',
        type=ParsedArgs.parse_input_path,
        help='Compile source file specified, or files found under a directory (default: `%(default)s`).',
        default='.' + pathsep)
    parser.add_argument('args', metavar='ARG', nargs='*', help='Command line arguments (for use with `--run`).')
    ns: ParsedArgs
    ns = parser.parse_args(args)  # type: ignore

    global_scope = AnalyzerScope.new_global_scope()
    with set_global_scope(global_scope):
        docs: list[Document] = list(load_std(ns.std))
        if ns.verbose:
            basicConfig(level=DEBUG)
        else:
            getLogger(__package__ + ".lexer").setLevel(level=ERROR)
        basicConfig(level=INFO)
        if ns.input.is_dir():
            docs.extend(discover_files(ns.input))
        else:
            docs.append(parse_file(ns.input))

        if ns.format:
            for doc in docs[1:]:
                print(f'```{doc.location.file}')
                print(''.join(x for x in doc.to_code()), end='')
            print('```')
            return

        errors = list(check_program(docs))

        if not ns.check_only and all(error.level.lower() not in ('error', 'critical') for error in errors):
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
    first = True
    for file, errors in errors_by_file.items():
        if file is not None:
            length = (50 - len(file)) // 2
            print('-' * length, file, '-' * length)
        elif not first:
            print('-' * 50)
        first = False
        for error in errors:
            render_error(error, verbose=ns.verbose)
            if error != errors[-1]:
                print('\033[0;2m-----+\033[0m')

    if error_count := sum(1 if error.level.lower() in ('error', 'critical') else 0 for error in errors):
        return error_count

    if ns.run:
        if binary is None:
            return -1

        from ..virtual_machine import VM
        vm = VM(binary, ns.args)
        try:
            vm.run()
        except VM.VmTerminated as ex:
            return ex.exit_code

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
