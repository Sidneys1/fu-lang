import sys
from argparse import ArgumentParser, FileType

from . import NAME
from .stream import StrStream, ListStream
from .tokenizer import Token
from .lexer import Body

from logging import getLogger, basicConfig, DEBUG

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

    token_stream = ListStream(tokens)
    lex = Body.try_lex(token_stream)
    print('```\n' + str(lex) + '```')

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
