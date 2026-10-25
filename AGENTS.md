# AGENTS.md

Guidance for coding agents working in Numlang.

## Project overview

- Primary executable: C++20 compiler `numlangc`, emitting C source.
- `numlang/` is the retained Python reference compiler, not the C++ implementation.
- The C++ port currently supports a limited core subset; see `docs/cpp-compiler-status.md`.
- Default branch: `main`.

## Working rules

- Inspect README.md, CMakeLists.txt, tests, and CI before editing.
- Keep C++ feature claims, tests, and capabilities.json synchronized.
- Fail closed for unsupported opcodes and source syntax.
- Do not claim the C++ port is feature-complete because the Python reference supports a feature.
- Keep build outputs and temporary compiler artifacts out of version control.
- Use feature branches and pull requests; never claim checks that were not run.
