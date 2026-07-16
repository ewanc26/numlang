# AGENTS.md

Guidance for agents working on Numlang, a Python compiler for a symbolic stack language that emits C.

## Compiler boundaries

- `numlang/` contains lexer, parser/AST, code generation, CLI, and diagnostics.
- `tests/` is the behavioral contract; `examples/` and `custom_programs/` are executable language examples.
- `.num` source syntax is public. Generated root `.c` files/binaries are examples or artifacts; keep source-of-truth relationships clear.

## Invariants

- Preserve token meanings, stack effects, source locations, numeric/coercion rules, and CLI exit codes.
- Validate stack underflow/overflow and malformed programs with useful diagnostics rather than emitting undefined C.
- Escape generated C strings/characters and never interpolate source text into shell commands.
- `--run` must use argument arrays and temporary directories safely, propagate compiler/runtime failure, and clean up.
- Keep output deterministic for identical input/options.

## Validation

Install editable with `pip install -e .`, run `pytest`, and run `python -m compileall numlang`. Compile representative examples with both the default C compiler and an alternate compiler when available; test invalid tokens, parse errors, stack boundaries, Unicode/escaping, custom stack size, token/AST dumps, and `--run` exit propagation. Do not commit caches or temporary binaries.
