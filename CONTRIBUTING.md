# Contributing to Numlang

Numlang is migrating from a feature-complete Python reference compiler to a C++20 compiler that emits C. The C++ port is intentionally incomplete; keep its supported subset explicit and fail clearly for unsupported operations.

## Development setup

A C++20 compiler, CMake, a host C compiler, Python 3, and pytest are required. The Python package is retained as a compatibility reference while the C++ port expands.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

## Working rules

- Read README.md, AGENTS.md, CMakeLists.txt, CI, and the C++ compiler-status document before changing behavior.
- Do not advertise a feature as implemented in C++ until the C++ compiler and a regression test cover it.
- Unsupported numeric opcodes and symbols must produce diagnostics, never silently compile as literals or no-ops.
- Keep the legacy Python tests passing when changing shared language semantics.
- Update the capability matrix to describe the C++ port, not only the legacy reference compiler.
- Add C++ end-to-end smoke coverage for new syntax and runtime behavior.
- Use a feature branch and pull request; report exact checks and results.
