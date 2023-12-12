# Switch Expression

## `?` Syntax

Parser:
```
DefaultSwitchCase:
    '_' '=>' Expression ';'
    ;

SwitchCase:
    Expression '=>' Expression ';'
    ;

Switch:
    '?' '{' SwitchCase+ DefaultSwitchCase? '}'
    ;
```

## Examples

### As an Expression

> ```
> x: foo = ? {
>   a_expression => a_value;
>   b_expression => b_value;
>   _ => default_value;
> };
> ```
> Equivalent C++ (using `int` as `foo`):
> ```cpp
> int x = a_expression ? a_value : (b_expression ? b_value : default_value);
> ```
> Also consider `return ? { ae => av; _ => dv; };` as equivalent to the C++ `return ae ? av : dv;`.

### As an Infix Operator

> ```
> x: foo = in_expression ? {
>   a_expression => a_value;
>   b_expression => b_value;
>   _ => default_value;
> };
> ```
> Equivalent C++ (using `int` as `foo`):
> ```cpp
> int x;
> {
>   // Create a temp for `in_expression` so it's only evaluated once.
>   auto temp = in_expression;
>   x = (temp == a_expression) ? a_value : ((temp == b_expression) ? b_value : default_value);
> }
> ```
