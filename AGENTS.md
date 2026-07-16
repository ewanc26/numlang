# AGENTS.md

Guidance for agents working on Numlang, a Python 3.10+ compiler for a numeric/punctuation stack language that emits C.

## Compiler pipeline and contracts

- `lexer.py` produces located tokens, byte-valued strings with C-style escapes, `|n`/`|nn` variable loads, integer/float literals, comments, and punctuation. Floats always push; integer values that collide with opcodes are reinterpreted by the parser.
- `parser.py` maps numeric opcodes, parses `/N ... ;` functions, `.N` calls, block-form IF/ELSE, WHILE, and REPEAT. A `/` followed by an integer begins a function definition, while integer 28 is an else separator only at the top level of an IF body.
- `sema.py` currently checks only undefined calls, empty WHILE/REPEAT bodies, and loaded variable bounds. It does not statically prove stack safety, reject duplicate function numbers, or validate every runtime domain condition.
- `codegen_c.py` emits a self-contained C99-style stack runtime with 100 variables, configurable stack size, math/bitwise/control/I/O operations, forward function declarations, and runtime checks. The checked-in `numlang/runtime.c` is only a vestigial comment; it is not included by code generation.
- `main.py` supports C output, `--run`, alternate compilers, stack size, token dumps, and AST dumps. It invokes the compiler with an argument array, uses a temporary directory, reports compiler failures, and propagates the generated program's exit code.
- `tests/test_compiler.py` covers lexer/parser/sema and GCC-backed end-to-end behavior; GCC-dependent tests skip when unavailable. Root generated `.c` files and executables are historical/manual fixtures, not the compiler source of truth.

## Invariants

- Keep README opcode tables, parser dispatch, codegen stack effects, examples, and tests synchronized. Preserve operand order, the 28/context rule, float escape from opcode collisions, REPEAT's pushed iteration index, and WHILE's consume-next-condition behavior.
- Preserve byte-oriented string semantics and document non-ASCII limitations. Validate shifts against the actual C `int` width; current `<64` checks can still permit undefined behavior on 32-bit `int`.
- Add semantic checks before relying on static safety; otherwise underflow/overflow and math domains remain runtime errors.
- Keep generated output deterministic except intentional `RAND`/`TIME` runtime behavior.

## Validation

Install with `pip install -e .`, run `pytest`, and run `python -m compileall numlang`. Compile every example/custom program and run non-interactive fixtures with GCC; sample Clang as a portability check. Cover duplicate functions, unterminated blocks, stack effects, opcode collisions, variable indices, all domain/shift boundaries, escapes, stack-size validation, debug dumps, compiler-not-found/failure, and child exit propagation. Do not commit caches or incidental binaries.
