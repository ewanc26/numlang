# Contributing to Numlang

An esoteric stack-based language whose entire character set is `0-9 ^ & * + - / . | ; % # ~ " !`, with an in-progress C++20 compiler that emits C. The historical Python compiler is retained as the reference implementation while C++ feature parity is rebuilt. Thanks for wanting to help!

## Getting started

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
# binary: build/numlangc
```

## Notes for this project

- **The Python compiler is the reference.** When the C++ path and the Python path disagree, the Python one is right by definition, until the language spec says otherwise — PRs should note any deliberate divergence.
- Check [`docs/cpp-compiler-status.md`](docs/cpp-compiler-status.md) before implementing anything: the status doc is the source of truth for what the C++ path covers (`numlangc` rejects recognized-but-unsupported structural opcodes rather than treating them as numbers; keep that property).
- Unusual correctness rules from the README are deliberate: string output preserving embedded NULs, explicit signed-shift behaviour, validated 32-bit ranges for bitwise opcodes. These came from bugs; don't undo them.
- Character set is closed: no new characters, ever — that's the whole language.

## Before opening a PR

- Build passes; the same program compiles and runs identically through `numlangc hello.num --run` and the Python reference path.
- Conventional commits; focused PRs; update the status doc in-PR.
- AI-assisted PRs welcome; stand behind every line and run both compilers yourself.

## Licence

See [LICENSE](LICENSE). Contributions accepted under the same terms.