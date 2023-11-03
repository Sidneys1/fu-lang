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
    files: list[Path] | None
    root: list[Path]
    std: Path

    @staticmethod
    def parse_files(string: str) -> Path:
        ret = Path(string).absolute()
        if not ret.is_file():
            raise ArgumentError(None, f"`{ret}` is not a file.")
        cwd = Path.cwd()
        if cwd != ret and cwd not in ret.parents:
            raise ArgumentError(None, f"`{ret}` is not in any subdirectory of current working directory `{cwd}`.")
        return ret  #.relative_to(cwd)

    @staticmethod
    def parse_root_path(string: str) -> Path:
        ret = Path(string).absolute()
        if not ret.is_dir():
            raise ArgumentError(None, f"`{ret}` is not a directory.")
        cwd = Path.cwd()
        if cwd != ret and cwd not in ret.parents:
            raise ArgumentError(None, f"`{ret}` is not a subdirectory of current working directory `{cwd}`.")
        return ret.relative_to(cwd)

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
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--std',
                        metavar='STD',
                        type=ParsedArgs.parse_std_path,
                        help="Path to the standard library (default: `%(default)s`).",
                        default=DEFAULT_STD_ROOT)
    positional = parser.add_mutually_exclusive_group(required=True)
    positional.add_argument('-f',
                            '--files',
                            metavar='FILE',
                            nargs='+',
                            type=ParsedArgs.parse_files,
                            help='Compile theses pecific source files. Mutually exclusive with `DIR`.')
    positional.add_argument(
        'root',
        metavar='DIR',
        nargs='*',
        type=ParsedArgs.parse_root_path,
        help=
        'Compile source files found under this directory (default: `%(default)s`). Mutually exclusive with `--files`.',
        default='.' + pathsep)
    ns: ParsedArgs
    ns, unknown_args = parser.parse_known_args(args)  # type: ignore

    if ns.verbose:
        basicConfig(level=DEBUG)
        _LOG.debug(f"Files: {ns.files}; Dirs: {ns.root}")
    else:
        getLogger(__package__ + ".lexer").setLevel(level=ERROR)
        basicConfig(level=INFO)

    global_scope = AnalyzerScope(None, AnalyzerScope.Type.Anonymous)
    with set_global_scope(global_scope):
        docs: list[Document] = list(load_std(ns.std))
        if ns.files is None:
            for root in ns.root:
                docs.extend(discover_files(root))
        else:
            for f in ns.files:
                docs.append(parse_file(f))
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
        vm = VM(binary, unknown_args)
        try:
            vm.run()
        except VM.VmTerminated as ex:
            return ex.exit_code

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
