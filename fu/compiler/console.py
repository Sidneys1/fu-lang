from io import SEEK_SET

from . import CompilerNotice


def render_error(error: CompilerNotice, indent: str = ''):
    if error.location.file is not None:
        fp = open(error.location.file)

    show_context = (not indent) and error.level.lower() not in ('note', 'info', 'debug')

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

        length = (rightmost - leftmost) + 1

        color = {'info': 96, 'warning': 33, 'warn': 33, 'error': 91, 'note': 0, 'debug': 2}.get(error.level.lower(), 45)
        if len(line) == length or not show_context:
            print(f'\033[0;{color}m <--', error.message, f'\033[0;2m({error.location})')
        else:
            print(f'\n\033[2m     |\033[;{color}m',
                  indent,
                  ' ' * leftmost,
                  '^' * length,
                  ' ',
                  f"{error.level}: {error.message}\033[0;2m ({error.location})",
                  sep='')

        for extra in error.extra:
            render_error(extra, indent=f'     |' + (' ' * (leftmost + length)) + f' > {extra.level}: ')

        line_no += 1
        line = fp.readline().rstrip()
        if show_context and line:
            print(f"{indent}\033[0;2m{line_no:>4}", '|', line, "\033[0m")
        else:
            print('\033[0m', end='')
    finally:
        fp.close()
        print('\033[m', end='', flush=True)
