<header align="center">
    <div align="center"><img height="100" src="https://openmoji.org/data/color/svg/1F94B.svg"/></div>
    <h1 align="center">Fu</h1>
    <div align="center">A Programming Language</div>
    <div align="center"><sup><sup>Aware&emsp;Alert&emsp;Kind&emsp;Simple&emsp;Opaque</sup></sup></div>
</header>
<blockquote width="100px" align="left" cite="https://www.mit.edu/~xela/tao.html">
    <p><i>
        The Tao gave birth to machine language. Machine language gave birth to the assembler.
        <br/>The assembler gave birth to the compiler. Now there are ten thousand languages.
        <br/>Each language has its purpose, however humble. Each language expresses the Yin and Yang of software.
        Each language has its place within the Tao.</p>
    </i></p>
    <div class="cite" align="right">
        &mdash;&nbsp;The Master Programmer, <i>The Tao of Programming</i> by Geoffrey James (1987)
    </div>
</blockquote>
<hr/>

```cpp
example: namespace = {
    hello: void() = {
        print("hello, word\n");
    };
};

[Entrypoint]
main: void() = {
    example.hello();
};
```

<h2 align="center">Tenets</h2>

#### Orthogonality

Patterns used in one place should be reused in others:

* Declarations will always be of form `name: type-sig`,
  read as: "name *is-a* type-sig".
  [^decl-always]
* Types can be suffixed with obvious modifiers, like `int[]` (int *array*), `void(int)` (void *when-called-with* an int).
* Assignment will always follow the pattern of `name = value`.

[^decl-always]: This pattern holds even when defining types, namespaces, and functions.

#### Intentionality

Code should always clearly convey intent:

* Declarations and type signatures are always **readable** and **unambiguous**.
* Statements should always be readable from left to right when transcribed to spoken words, so `ordinals: str[](int[])`
  is read as "ordinals *is-a* string *array* *when-called-with* an int *array*".
* Function types are `return-type(param-name: param-type[, ...])`,
  read as: "return-type, *when-called-with*: param-name *is-a* param-type".
  [^todo-nameless-parameters]

[^todo-nameless-parameters]: Currently, all callable types' parameters must have names.

    For example, you can say `foo: void(a: int)`, but not `foo: void(int)`.

    *In the future*[^todo], names will still be required when *assigning* a function, but not when *declaring* one
    <u>without defining it</u>, or when specifying an inner type:

    <table>
    <tr><td>✅</td><td><samp>foo: void(logger: void(str)) = { logger("message"); };</samp></td></trs>
    <tr><td>❌</td><td><samp>foo: void(void(str)) = {/* How do I know how to access the logger? */};</samp></td></tr>
    </table>

#### Opt-*Out* Async[^todo]

Async/await patterned programming enables performant, block-free code:

* The entire program will be run in an async executor, unless you opt-out.[^opt-out-async]
* Async state is stored on the stack.

[^opt-out-async]: *In the future*[^todo] the `[Entrypoint]` metadata decorator will support something like
    `[Entrypoint(async=false)]`. *However*, <u>all blocking standard library functions will be async</u>, so there will
    be additional work required to have a synchronous entrypoint.

#### Concurrent Safety Aware[^todo]

Static analysis will be aware (to the extent it can be) of concurrent safety:

* Primitive containers and other data types provided by the standard library will be annotated with static type metadata
  exposing whether they are safe to use in concurrent programming.

#### Copy-Free First

Data passing will prefer references with explicit mutability over unnecessary copying.

#### C-String Free

C-style strings (null-terminated strings) are not supported. Instead:

* The language will have first-class support for views/ranges/slicing.
* String types will be lightweight views over byte buffers.
  * Variable width Unicode support comes naturally with the use of performant iterators[^branchless-unicode].

[^branchless-unicode]: [<q>A Branchless UTF-8 Decoder</q>](https://nullprogram.com/blog/2017/10/06/) &mdash;&nbsp;Chris Wellons, *null program* (2017).

<h2  align="center">Examples</h2>

#### Orthogonality Examples

##### Declarations of form <samp>name: type</samp>

<table align="center">
<tr><td>Variables</td>
<td width="500px">

```cpp
foo: str;
bar: int = 0;
```

</td>
</tr>
<!--  -->
<tr><td title="Namespaces must be initialized with a body.">

Namespaces[^nmspc-init-reqd][^dotted-nmspc]</td>
<td width="500px">

```cpp
example.impl: namespace = {
};
```
</td>
</tr>
<!--  -->
<tr><td>Functions</td>
<td width="500px">

```cpp
main: void(args: str[]) = {
    print("hello, world!");
};
```
</td>
</tr>
</table>

[^nmspc-init-reqd]: Namespaces *must* be initialized with a body.
[^dotted-nmspc]: Namespaces with dotted names is syntactically equivalent to defining them separately:

    ```cpp
    example.impl: namespace = {};
    // Same as:
    example: namespace = {
    impl: namespace = {};
    };
    ```

[^todo]: <u>This is a future feature that is not yet supported.</u>