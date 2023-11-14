import sys
from argparse import ArgumentError, ArgumentParser
from logging import DEBUG, ERROR, INFO, basicConfig, getLogger
from pathlib import Path
from typing import Protocol

from ..virtual_machine.bytecode.structures.binary import BytecodeBinary

from . import NAME
from .analyzer import check_program
from .analyzer.scope import AnalyzerScope, set_global_scope
from .console import render_error
from .discovery import DEFAULT_STD_ROOT, discover_files, load_std, parse_file
from .lexer import Document

_LOG = getLogger(__package__)

class CompilerParsedArgs(Protocol):
    run: bool
    verbose: bool
    check_only: bool
    format: bool
    input: Path
    std: Path
    output: Path
    args: list[str]

    @staticmethod
    def parse_input_path(string: str) -> Path:
        ret = Path(string).absolute()
        cwd = Path.cwd()
        if cwd != ret and cwd not in ret.parents:
            raise ArgumentError(None, f"`{ret}` is not under the current working directory `{cwd}`.")
        return ret

    @staticmethod
    def parse_output_path(string: str) -> Path:
        ret = Path(string).absolute()
        if ret.exists():
            cwd = Path.cwd()
            read = input(f"Output file `{ret.relative_to(cwd, walk_up=True)}` already exist. Replace? [Yn] ")
            if read.lower() not in ('y', 'yes'):
                raise ArgumentError(None, 'Output file already exists.')
        return ret

    @staticmethod
    def parse_std_path(string: str) -> Path:
        ret = Path(string).absolute()
        if not ret.is_dir():
            raise ArgumentError(None, f"`{ret}` is not a directory.")
        if not (ret / '__builtins__.fu').is_file():
            raise ArgumentError(None, f"`{ret}` does not contain `__builtins__.fu`.")
        return ret


class CompilerParser(Protocol):
    def parse_args(self) -> CompilerParsedArgs:
        ...

def make_compiler_parser() -> CompilerParser:
    parser = ArgumentParser(NAME, description='Parse, check, and compile a Fu program.')

    group = parser.add_mutually_exclusive_group()

    group.add_argument('-c', '--check-only', help="Stop after checking.", action='store_true')
    group.add_argument('-f', '--format', help=" Print a formatted version of the input file before checking and exit.", action='store_true')
    group.add_argument('-r', '--run', help="Run the built code after compiling.", action='store_true')

    build_options = parser.add_argument_group("Build Options")
    build_options.add_argument('-o', '--output', metavar='PATH', help="Output file path (default: `%(default)s`).", type=CompilerParsedArgs.parse_output_path, default=Path('./a.out'))
    build_options.add_argument('--std',
                        metavar='STD_PATH',
                        type=CompilerParsedArgs.parse_std_path,
                        help="Path to the standard library (default: `%(default)s`).",
                        default=DEFAULT_STD_ROOT)

    output_options = parser.add_argument_group('Output Options')
    output_options.add_argument('-v', '--verbose', action='store_true')

    parser.add_argument(
        'input',
        metavar='PATH',
        type=CompilerParsedArgs.parse_input_path,
        help='Compile source file specified, or files found under a directory (default: `%(default)s`).',
        default=Path('.'))
    parser.add_argument('args', metavar='ARG', nargs='*', help='Command line arguments (for use with `--run`).')

    return parser  # type: ignore

def main(ns: CompilerParsedArgs) -> int:
    global_scope = AnalyzerScope.new_global_scope()
    binary: BytecodeBinary | None = None
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
            return 0

        errors = list(check_program(docs))

        if not ns.check_only and all(error.level.lower() not in ('error', 'critical') for error in errors):
            from .compile import compile
            from .util import collect_returning_generator


            binary, c_errors = collect_returning_generator(compile())
            errors.extend(c_errors)

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

    if binary is None:
        return -1

    assert isinstance(binary, BytecodeBinary)
    with open('a.out', 'wb+') as output:
        binary.encode(output)
        from humanize.filesize import naturalsize
        _LOG.info(f"Output binary `a.out`: {naturalsize(output.tell(), binary=True, format="%.02f")}")

    if ns.run:
        from ..virtual_machine import VM
        vm = VM(binary, ns.args)
        try:
            vm.run()
        except VM.VmTerminated as ex:
            return ex.exit_code

    return 0


def _main() -> int:
    return main(make_compiler_parser().parse_args())

if __name__ == '__main__':
    sys.exit(_main())
