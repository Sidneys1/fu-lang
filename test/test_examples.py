def test_examples(global_scope):
    from fu.compiler.discovery import discover_files, DEFAULT_STD_ROOT, parse_file
    from fu.compiler.analyzer import check_program
    builtins = builtins = parse_file(DEFAULT_STD_ROOT / '__builtins__.fu')
    program = list(discover_files(DEFAULT_STD_ROOT / '..' / 'examples'))
    program.insert(0, builtins)
    errors = list(check_program(program))
    assert all(e.level.lower() not in ('error', ) for e in errors if e.level.lower())
