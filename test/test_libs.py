def test_builtins():
    from fu.compiler.discovery import parse_file, DEFAULT_STD_ROOT
    parse_file(DEFAULT_STD_ROOT / '__builtins__.fu')


def test_check_builtins():
    from fu.compiler.discovery import parse_file, DEFAULT_STD_ROOT
    from fu.compiler.analyzer import check_program
    builtins = parse_file(DEFAULT_STD_ROOT / '__builtins__.fu')
    for n in check_program([builtins]):
        print(n)
