import sys
from argparse import ArgumentParser, FileType
from logging import getLogger, basicConfig, DEBUG

from . import NAME
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
    str_stream = StrStream(ns.FILE)

    tokens = []
    for token in Token.token_generator(str_stream):
        print(" -", token)
        tokens.append(token)
    if not str_stream.eof:
        print(f"Failed at: {str_stream.tail!r}")
        return 1
    print(str_stream.efficiency)

    token_stream = TokenStream(tokens)

    lex = parse(token_stream)
    if not token_stream.eof:
        print(f"Failed at: {token_stream.peek()}")
        return 1
    if lex is None:
        print(f'Failed to lex.')
        return 1

    print(token_stream.efficiency)

    lex.unrepr()
    # print(lex.s_expr())
    print('```\n' + str(lex) + '```')
    lex.check()

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
