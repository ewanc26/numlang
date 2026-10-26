# C++ compiler status

This document describes the C++ `numlangc` implementation. The historical Python compiler under `numlang/` is retained as a reference and is tested separately; its feature coverage must not be attributed to the C++ executable.

## Supported end-to-end subset

- Numeric literals: decimal integers/floats plus basic hex, octal, and binary forms.
- String literals with common C escapes; single-byte character literals with basic escapes.
- Stack operations: `16` DUP, `17` SWAP, `18` DROP.
- Arithmetic: `+`, `-`, `*`, `/`, `%` with runtime zero checks.
- Comparisons: `10`–`15`; logical OR/AND `19` and `39`; logical NOT `!`.
- Math and bitwise opcodes implemented by the C++ code generator: `21`–`27`, `29`, `31`–`49`; integer bitwise operations use checked 32-bit conversions, explicit shift semantics, and overflow diagnostics.
- Numbered variables: `|n` loads and `&` stores a value to the index on top of the stack.
- Console I/O: `|` prints a number, `^` prints a character, `?` reads a number, and strings write directly to stdout.
- CLI: `-o/--output`, `--run`, `--cc`, `--stack-size`, and `--support`. `--run` uses a unique temporary directory and shell-quotes executable and file paths.

## Explicitly deferred

Control-flow opcodes (`20`, `28`, `30`, `50`), array operations (`51`–`53`), integer division (`55`), miscellaneous runtime opcodes (`60`–`64`), type declarations/conversions, named functions and variables, FFI, pointers, structs/unions, and the broader C-like type system are not implemented in C++ yet. Known reserved opcodes fail with a compile-time diagnostic instead of being emitted as numeric pushes.

Escape decoding, integer suffixes, C type conversions, stack-depth introspection, and full error/semantic parity are also incomplete. Do not extend the capability matrix to `implemented` for these features until there are C++ end-to-end tests.

## Verification

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

The CTest suite runs `tests/smoke_cpp.py` against the C++ binary and the legacy Python unit suite in `tests/test_compiler.py`. Full C++ differential parity is still outstanding.
