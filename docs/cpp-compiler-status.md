# C++ compiler status

This document describes the C++ `numlangc` implementation. The historical Python compiler under `numlang/` is retained as a reference and is tested separately; its feature coverage must not be attributed to the C++ executable.

## Supported end-to-end subset

- Numeric literals: decimal integers/floats plus basic hex, octal, and binary forms.
- String literals with common C escapes, including embedded NUL bytes preserved by length-aware output; single-byte character literals with basic escapes.
- Stack operations: `16` DUP, `17` SWAP, `18` DROP.
- Arithmetic: `+`, `-`, `*`, `/`, `%` with runtime zero checks.
- Comparisons: `10`–`15`; logical OR/AND `19` and `39`; logical NOT `!`.
- Math and bitwise opcodes implemented by the C++ code generator: `21`–`27`, `29`, `31`–`49`; integer bitwise operations use checked 32-bit conversions, explicit signed-shift behavior, and diagnostics for out-of-range values and remainder overflow.
- Integer division `55` (IDIV): checked 32-bit operands, C truncation toward zero, with diagnostics for division by zero and `INT32_MIN / -1` overflow.
- Runtime opcodes: `60` RAND pushes a double in `[0, 1)`, `61` TIME pushes the Unix timestamp as a double, `62` EXIT pops an exit code and terminates, `63` DEPTH pushes the stack depth, and `64` PICK pops an index and copies that stack element to the top with a range diagnostic.
- Numbered variables: `|n` loads and `&` stores a value to the index on top of the stack.
- Foreign C functions: `@N "header" "symbol" arity ;` declares and `$N` calls (arity 0-3), matching the reference design. System headers are included in the generated C; a `.c` header is `#include`d directly with a `double`-parameter declaration rather than compiled and linked separately as the Python reference does.
- Console I/O: `|` prints a number newline-terminated in shortest `%g` style, `^` prints a character, `?` reads a number, and strings write directly to stdout.
- CLI: `-o/--output`, `--run`, `--cc`, `--stack-size`, and `--support`. `--run` uses a unique temporary directory and shell-quotes executable and file paths.

## Explicitly deferred

Control-flow opcodes (`20`, `28`, `30`, `50`), array operations (`51`–`53`), type declarations/conversions, named functions and variables, FFI, pointers, structs/unions, and the broader C-like type system are not implemented in C++ yet. Known reserved opcodes fail with a compile-time diagnostic instead of being emitted as numeric pushes.

Full C escape-decoding parity, integer suffix/type semantics, C type conversions, stack-depth introspection, and full error/semantic parity are also incomplete. Do not extend the capability matrix to `implemented` for these features until there are C++ end-to-end tests.

## Verification

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

The CTest suite runs `tests/smoke_cpp.py` against the C++ binary and the legacy Python unit suite in `tests/test_compiler.py`. Full C++ differential parity is still outstanding.
