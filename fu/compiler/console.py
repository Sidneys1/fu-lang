from inspect import FrameInfo
from io import SEEK_SET
from typing import Any

from . import CompilerNotice

_RESET = 0
_BRIGHT = 60
_CYAN = 36
_YELLOW = 33
_RED = 31
_FAINT = 2
_MAGENTA = 35
_REVERSE = 7

_COLOR_MAP: dict[CompilerNotice.Level, Any] = {
    CompilerNotice.Level.Info: _BRIGHT + _CYAN,
    CompilerNotice.Level.Warning: _YELLOW,
    CompilerNotice.Level.Error: _BRIGHT + _RED,
    CompilerNotice.Level.Note: _RESET,
    CompilerNotice.Level.Debug: _FAINT,
    CompilerNotice.Level.Critical: f'{_MAGENTA};{_REVERSE}'
}


def _frame(frames: list[FrameInfo]) -> str:
    return "created at:\n\t" + '\n\t'.join(f"{frame.filename}:{frame.lineno}, {frame.function}"
                                           for frame in frames) + '\n'


def render_error(error: CompilerNotice, indent: str = '', verbose: bool = False):
    message_color = _COLOR_MAP.get(error.level, 45)
    if error.location is None:
        location = f" ({_frame(error._source)})" if verbose else ''
        print(f'  \033[{message_color}m', indent, f"{error.level.name}: {error.message}\033[0;2m{location}", sep='')
        for extra in error.extra:
            render_error(extra, indent=f'   > {extra.level.name}: ', verbose=verbose)
        return

    fp = open(error.location.file)

    show_context = (not indent) and error.level.value not in ('note', 'info', 'debug')

    try:
        fp.seek(0, SEEK_SET)

        line_no = 1
        line_color = 2 if indent or not show_context else 1
        if error.location.lines[0] > 1:
            line = fp.readline()
            while line_no < (error.location.lines[0] - 1):
                line_no += 1
                line = fp.readline()
            if show_context and (line := line.rstrip()):
                print(f"{indent}\033[2m{line_no:>4}", '|', line, end='\033[0m\n')

        leftmost = min(*error.location.columns)
        rightmost = max(*error.location.columns)

        line = fp.readline().rstrip()
        first_left = error.location.columns[0]
        first_right = error.location.columns[1] if error.location.lines[0] == error.location.lines[1] else len(line)
        line_no += 1
        if indent:
            print(f"{indent}\033[2m",
                  f'|',
                  line[:first_left - 1] + f'\033[0;{line_color}m' + line[first_left - 1:first_right] + '\033[2m' +
                  line[first_right:],
                  end='\033[0m')
        else:
            print(f"{indent}\033[2m{line_no:>4}",
                  f'|',
                  line[:first_left - 1] + f'\033[0;{line_color}m' + line[first_left - 1:first_right] + '\033[2m' +
                  line[first_right:],
                  end='\033[0m')
        while line_no < (error.location.lines[1] - 1):
            line = fp.readline().rstrip()
            line_no += 1
            print(f"\n{indent}\033[2m{line_no:>4}", f'|\033[0;{line_color}m', line, end='\033[0m')

        if line_no < error.location.lines[1]:
            line = fp.readline().rstrip()
            last_left = error.location.columns[1] if error.location.lines[0] == error.location.lines[0] else 0
            last_right = error.location.columns[1]
            line_no += 1
            print(f"\n{indent}\033[2m{line_no:>4}",
                  f'|',
                  line[:last_left - 1] + f'\033[0;{line_color}m' + line[last_left - 1:last_right] + '\033[2m' +
                  line[last_right:],
                  end='\033[0m')

        length = (rightmost - leftmost) + 1\

        if len(line) == length or not show_context:
            location = f"{error.location} / {_frame(error._source)}" if verbose else str(error.location)
            print(f'\033[0;{message_color}m <--', error.message, f'\033[0;2m({location})')
        else:
            location = f"{error.location} / {_frame(error._source)}" if verbose else str(error.location)
            print(f'\n\033[2m     |\033[;{message_color}m',
                  indent,
                  ' ' * leftmost,
                  '^' * length,
                  ' ',
                  f"{error.level.name}: {error.message}\033[0;2m ({location})",
                  sep='')

        # if isinstance(error.extra, CompilerNotice):
        #     raise RuntimeError(_frame(error.extra._source))
        for extra in error.extra:
            render_error(extra, indent=f'     |' + (' ' * (leftmost + length)) + f' > {extra.level}: ', verbose=verbose)

        line_no += 1
        line = fp.readline().rstrip()
        if show_context and line:
            print(f"{indent}\033[0;2m{line_no:>4}", '|', line, "\033[0m")
        else:
            print('\033[0m', end='')
    finally:
        fp.close()
        print('\033[m', end='', flush=True)
