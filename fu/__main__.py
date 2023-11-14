import sys
from pathlib import Path
from typing import Protocol, Literal, TYPE_CHECKING
from argparse import ArgumentParser, ArgumentError

from . import NAME
from .compiler.__main__ import make_compiler_parser, CompilerParsedArgs, main as compiler_main

if TYPE_CHECKING:
    from .virtual_machine.bytecode.structures.binary import BytecodeBinary


class FuArgumentParser(Protocol):

    class ParsedArgs(CompilerParsedArgs, Protocol):
        cmd: Literal['build', 'run']
        file: Path
        args: list[str]
        disassemble: bool
        function: str

        @staticmethod
        def parse_path(value: str) -> Path:
            path = Path(value)
            if not path.is_file():
                raise ArgumentError(None, 'Input is not a file')
            return path

    def parse_args(self) -> ParsedArgs:
        ...


def _make_disassembly_parser() -> ArgumentParser:
    parser = ArgumentParser(add_help=False)
    # parser.add_argument('-f', '--function', metavar='NAME', help='Only disassemble a specific function.')
    return parser


def _make_parser() -> FuArgumentParser:
    disassembly_parser = _make_disassembly_parser()

    parser = ArgumentParser(NAME, description='The Fu compiler and runtime.')
    subparsers = parser.add_subparsers(dest='cmd', required=True)
    subparsers.add_parser(
        'build',
        help='Build a Fu program from source.',
        parents=(
            make_compiler_parser(),  # type: ignore
        ),
        add_help=False)
    run = subparsers.add_parser('run', help='Run a compiled Fu program.', parents=(disassembly_parser, ))
    run.add_argument('file', metavar='FILE', type=FuArgumentParser.ParsedArgs.parse_path, help='Fu binary to run.')
    run.add_argument('args', metavar='ARG', nargs='*', help='Command line to pass to the Fu binary.')
    run.add_argument('-d', '--disassemble', action='store_true', help='Show program disassembly before running.')

    disassemble = subparsers.add_parser('disassemble',
                                        aliases=('asm', ),
                                        help='Show the disassembly of a Fu program.',
                                        parents=(disassembly_parser, ))
    disassemble.add_argument('file',
                             metavar='FILE',
                             type=FuArgumentParser.ParsedArgs.parse_path,
                             help='Fu binary to disassemble.')

    info = subparsers.add_parser('info')
    info.add_argument('file',
                      metavar='FILE',
                      type=FuArgumentParser.ParsedArgs.parse_path,
                      help='Fu binary to show info for.')
    return parser  # type: ignore


def _show_disassembly(args: FuArgumentParser.ParsedArgs, binary: 'BytecodeBinary') -> None:
    from .virtual_machine.bytecode.decompiler import decompile
    # single_func = args.function is not None
    # addr = 0 if args.function is None else next(x.addr for x in binary.functions if x.name == args.function)
    for line in decompile(binary.bytecode, binary=binary):
        print('%     ', line, sep='')


def main() -> int:
    ns = _make_parser().parse_args()
    if ns.cmd == 'build':
        compiler_main(ns)
    elif ns.cmd == 'run':
        from .virtual_machine.bytecode.structures.binary import BytecodeBinary
        with ns.file.open('rb') as file:
            binary = BytecodeBinary.decode(file)
        if ns.disassemble:
            _show_disassembly(ns, binary)
            input('% Press enter to run...')
        from .virtual_machine import VM
        vm = VM(binary, ns.args)
        try:
            vm.run()
        except VM.VmTerminated as ex:
            return ex.exit_code
    elif ns.cmd in ('disassemble', 'asm'):
        from .virtual_machine.bytecode.structures.binary import BytecodeBinary
        with ns.file.open('rb') as file:
            binary = BytecodeBinary.decode(file)
        _show_disassembly(ns, binary)
    elif ns.cmd == 'info':
        from humanize.filesize import naturalsize
        from .virtual_machine.bytecode.structures.binary import BytecodeBinary
        with ns.file.open('rb') as file:
            binary = BytecodeBinary.decode(file)
        print('Flags:\t\t',
              ('None' if binary.flags == BytecodeBinary.Flags.NONE else ', '.join(x.name for x in binary.flags)), ' (1 byte)',
              sep='')
        if BytecodeBinary.Flags.IS_LIBRARY not in binary.flags:
            print(f'Entrypoint:\t{binary.entrypoint:#010x} (4 bytes)')
        strings_count = binary.strings_count
        size = len(binary.strings) - (4 * strings_count)
        print(f'Strings:\t{binary.strings_count:,} ({naturalsize(size, True, format='%.2f')} total)')
        print(f'Bytecode:\t{len(binary.functions):,} functions ({naturalsize(len(binary.bytecode), True, format='%.2f')} total)')
        print(f'Debug info:\t{len(binary.source_map):,} bytecode-to-source maps ({naturalsize(28 * len(binary.source_map) + sum(len(x.file.encode('utf-8')) for x in binary.source_map), True, format='%.2f')} total)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
