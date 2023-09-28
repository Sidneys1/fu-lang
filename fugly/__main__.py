import sys
from argparse import ArgumentParser, FileType
from io import SEEK_SET
from logging import getLogger, basicConfig, DEBUG, INFO
from pathlib import Path

from . import NAME, SourceLocation, CompilerNotice, SourceFile
from .stream import StrStream, TokenStream
from .tokenizer import Token
from .lexer import parse

_LOG = getLogger()
_LOG.setLevel(DEBUG)
basicConfig(level=DEBUG)
_LOG.propagate = True


def main(*args) -> int:
    parser = ArgumentParser(NAME)
    parser.add_argument('FILE', type=FileType())
    ns = parser.parse_args(args)
    SourceFile.set(str(Path(ns.FILE.name).absolute().relative_to(Path.cwd())))
    str_stream = StrStream(ns.FILE)

    token_stream = TokenStream([], generator=Token.token_generator(str_stream))

    lex = parse(token_stream)
    peeks, pops = str_stream.efficiency
    print(f"Chars: {peeks=}, {pops=}, {pops/(pops+peeks):0.2%}")
    peeks, pops = token_stream.efficiency
    print(f"Tokens: {peeks=}, {pops=}, {pops/(pops+peeks):0.2%}")
    if not token_stream.eof:
        print(f"Failed at: {token_stream.peek()}")
        return 1
    if lex is None:
        print(f'Failed to lex.')
        return 1

    for klass, calls in sorted(token_stream._who_called.items(), key=lambda t: t[1], reverse=True):
        print(klass.__name__, calls)

    print('```\n' + str(lex) + '```')

    lex.unrepr()

    def error_range(error: CompilerNotice, indent: str = ''):
        ns.FILE.seek(0, SEEK_SET)

        file = f"{error.location.file}:" if error.location.file is not None else ''

        line_no = 1
        line_color = 2 if indent else 1
        if error.location.lines[0] > 1:
            line = ns.FILE.readline()
            while line_no < (error.location.lines[0] - 1):
                line_no += 1
                line = ns.FILE.readline()
            if not indent and (line := line.rstrip()):
                loc = f"{file}{line_no}"
                print(f"{indent}\033[2m{loc:>10}", '|', line, '\033[0m')

        length = error.location.columns[1] - error.location.columns[0] + 1

        line = ns.FILE.readline().rstrip()
        line_no += 1
        color = {'info': 96, 'warning': 33, 'warn': 33, 'error': 91, 'note': 2}.get(error.level.lower(), 45)
        loc = f"{file}{line_no}"
        print(f"{indent}\033[2m{loc:>10}", f'|\033[0m\033[{line_color}m', line, end=f'\033[0m\033[{color}m')
        if len(line) == length:
            print(' <--', error.message, '\033[0m\033[2m', error.location)
        else:
            print('\n',
                  indent,
                  ' ' * (error.location.columns[0] + 12),
                  '^' * length,
                  ' ',
                  f"{error.level}: {error.message} \033[0m\033[2m({error.location})",
                  sep='')
        if error.extra is not None:
            error_range(error.extra, indent=(' ' * (14 + length)) + '>')
        line_no += 1
        line = ns.FILE.readline().rstrip()
        if not indent and line:
            loc = f"{file}{line_no}"
            print(f"{indent}\033[0m\033[2m{loc:>10}", '|', line, "\033[0m")
        else:
            print('\033[0m', end='')

    from .analyzer import check_program
    for error in check_program([lex]):
        if error.level in ('Note', ):
            print(f"\033[92m{error.level:>7}: {error.message} \033[0m({error.location})")
        else:
            error_range(error)

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
