from pathlib import Path
from subprocess import Popen, PIPE
from sys import executable
from difflib import Differ

from pytest import mark

FILE = Path(__file__)
FILES = (FILE.parent / 'regression').glob('*.fu')
ROOT = FILE.parent.parent.absolute()


@mark.parametrize('file', FILES, ids=lambda x: x.stem)
def test_regression(file: Path):
    expected_stdout_file = (file / '..' / 'output' / (file.name + '.stdout')).resolve()
    expected_stderr_file = (file / '..' / 'output' / (file.name + '.stderr')).resolve()
    assert expected_stderr_file.is_file()
    assert expected_stdout_file.is_file()
    with Popen([executable, '-m', 'fu.compiler', '-f', str(file.absolute())],
               stdout=PIPE,
               stderr=PIPE,
               cwd=str(ROOT)) as compiler:
        stdout, stderr = compiler.communicate(timeout=10.0)

    diffs = '\n\t'.join(f"Line {i}: {line[0:2]}{line[2:]!r}" for i, line in enumerate(Differ().compare(
        expected_stderr_file.read_bytes().decode("utf-8", "strict").split('\n'), stderr.decode("utf-8", "strict").split('\n')))
                        if line[0:2] in ('- ', '+ '))
    if diffs:
        assert False, "Input and output differ (stderr):\n\t" + diffs+ f"\n\n----------\n{stderr.decode("utf-8", "strict")}----------vs----------\n{expected_stderr_file.read_text("utf-8", "strict")}----------"

    diffs = '\n\t'.join(f"Line {i}: {line[0:2]}{line[2:]!r}" for i, line in enumerate(Differ().compare(
        expected_stdout_file.read_bytes().decode("utf-8", "strict").split('\n'), stdout.decode("utf-8", "strict").split('\n')))
                        if line[0:2] in ('- ', '+ ')
                        )
    if diffs:  # any(d[0:2] in ('- ', '+ ') for d in diffs)
        assert False, "Input and output differ (stdout):\n\t" + diffs + f"\n\n----------\n{stdout.decode("utf-8", "strict")}----------vs----------\n{expected_stdout_file.read_bytes().decode("utf-8", "strict")}----------"
