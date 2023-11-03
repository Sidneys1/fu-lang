from typing import cast

from conftest import FakeFile
from pytest import mark, raises

FAKE_NAMESPACE = """foo: namespace = { bar: namespace = { }; };"""
FAKE_NAMESPACE_DUPE = """foo: namespace = { }; foo: namespace = {}; main: void() = {}; main: namespace = {};"""

FAKE_TYPE = """foo: type = { };"""
FAKE_TYPE_EXISTS = """foo: namespace = {}; foo: type;"""
FAKE_TYPE_SHADOWS = """foo: namespace = { i32: type; };"""
FAKE_TYPE_FORWARD = """foo: type;"""
FAKE_TYPE_COMPLEX = """foo: type = { x: u8 = 0; };"""
FAKE_TYPE_SUBTYPE = """foo: type = { bar: type = { }; };"""
FAKE_TYPE_CTOR = """foo: type = { op=: this() = { }; };"""
FAKE_TYPE_UNASSIGNED = """foo: type = { x: i8; op=: this() = { y: i8 = 0; }; };"""
FAKE_TYPE_ASSIGNED = """foo: type = { x: usize_t; op=: this() = { .x = 0; }; };"""
FAKE_TYPE_CTOR_RETURN = """foo: type = { op=: this() = { return 0; }; };"""

FAKE_DECL = """main: void() = { x: i8 = 0; };"""
FAKE_DECL_SHADOWS = """x: namespace = {}; main: void() = { x: i8 = 0; };"""
FAKE_DECL_CONVERSION = """x: u8 = 500;"""
FAKE_DECL_TYPES = """foo: type = {}; x: foo = (0);"""
FAKE_DECL_STATEMENT = """foo: i8(x: i8, y: i8) = { return x + y; };"""
FAKE_DECL_REDECL = """x: i8; x: u8;"""
FAKE_DECL_BADBODY = """x: i8 = { };"""
FAKE_DECL_EMPTY_BODY = """main: void() = { };"""

FAKE_CONVERSION_VOID = """main: void() = { x: void = 0; };"""
# FAKE_CONVERSION_BOOL = """Foo: type = {}; main: void(x: Foo) = { y: bool = x; };"""  # not implemented
FAKE_CONVERSION_FLOAT_INT = """main: void(x: f32) = { y: u8 = x; };"""
FAKE_CONVERSION_FLOAT_FLOAT_BAD = """main: void(x: f32) = { y: f16 = x; };"""
FAKE_CONVERSION_FLOAT_FLOAT_GOOD = """main: void(x: f16) = { y: f32 = x; };"""
# FAKE_CONVERSION_INT_FLOAT = """main: void(x: u8) = { y: f16 = x; };"""  # Not implementedy

FAKE_FILES = (
    (FAKE_NAMESPACE, ..., ()),
    (FAKE_NAMESPACE_DUPE, "'main' already exists in <GLOBAL SCOPE>!", ()),
    (FAKE_TYPE, ..., ()),
    (FAKE_TYPE_EXISTS, "`foo` already defined.", ()),
    (FAKE_TYPE_SHADOWS, "`i32` shadows existing type.", ()),
    (FAKE_TYPE_FORWARD, "Cannot forward-declare types. Please provide an assignment.", ()),
    (FAKE_TYPE_COMPLEX, ..., ()),
    (FAKE_TYPE_SUBTYPE, ..., ()),
    (FAKE_TYPE_CTOR, ..., ()),
    (FAKE_TYPE_UNASSIGNED, ..., ("Constructor for `foo` does not initialize members `x`.", )),
    (FAKE_TYPE_ASSIGNED, ..., ()),
    (FAKE_TYPE_CTOR_RETURN, ..., ("Returning values not allowed in a constructor!", )),
    (FAKE_DECL, ..., ()),
    (FAKE_DECL_SHADOWS, ..., ("Declaration of 'x' shadows previous declaration.",
                              "'x' is shadowing an existing identifier!")),
    (FAKE_DECL_CONVERSION, ...,
     ("Narrowing when implicitly converting from a `usize_t` (64bit unsigned) to a `u8` (8bit unsigned).", )),
    (FAKE_DECL_TYPES, ..., ()),
    (FAKE_DECL_STATEMENT, ..., ("Checks for infix operator '+' are not implemented!", )),
    (FAKE_DECL_REDECL, ..., ("Redefinition of 'x'.", )),
    (FAKE_DECL_BADBODY, "`x: i8` is not callable but is initialized with a body.", ()),
    (FAKE_DECL_EMPTY_BODY, ..., ("Method initialized with an empty body.", )),
    (FAKE_CONVERSION_VOID, ..., ("There are no conversions to or from void.", )),
    # (FAKE_CONVERSION_BOOL, ..., ()),
    (FAKE_CONVERSION_FLOAT_INT, ..., ("Loss of precision converting from a `f32` to a `u8`.", )),
    (FAKE_CONVERSION_FLOAT_FLOAT_BAD, ..., ("Loss of floating point precision converting from a `f32` to a `f16`.", )),
    (FAKE_CONVERSION_FLOAT_FLOAT_GOOD, ..., ()),
)


@mark.parametrize('content,expect,warnings', FAKE_FILES)
def test_analysis(global_scope, content, expect, warnings):
    from fu.compiler import ImmutableTokenStream, CompilerNotice
    from fu.compiler.stream import TokenStream, StrStream
    from fu.compiler.tokenizer import Token
    from fu.compiler.lexer import parse
    from fu.compiler.discovery import DEFAULT_STD_ROOT, parse_file
    from fu.compiler.analyzer import check_program

    with FakeFile('empty.py', content) as file:
        stream = TokenStream([], generator=Token.token_generator(StrStream(file)))
        builtins = builtins = parse_file(DEFAULT_STD_ROOT / '__builtins__.fu')
        program = [builtins, parse(cast(ImmutableTokenStream, stream))]
        assert all(x is not None for x in program)
        if expect is not Ellipsis:
            with raises(CompilerNotice, match=expect):
                errors = list(check_program(program))
                for expected in warnings:
                    found = None
                    for error in errors:
                        if error.message == expected:
                            found = error
                            break
                    if found is None:
                        assert False, f"Missing expected error: {expected}"
                    errors.remove(found)
                assert not errors
        else:
            errors = list(check_program(program))
            for expected in warnings:
                found = None
                for error in errors:
                    if error.message == expected:
                        found = error
                        break
                if found is None:
                    assert False, f"Missing expected error: {expected}"
                errors.remove(found)
            assert not errors
