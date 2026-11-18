# AGENTS.md

Guidance for AI coding agents working in **numlang**.

## Project overview

Numlang is an esoteric stack-based language with an in-progress C++20 compiler that emits C. The historical Python compiler is retained as a reference implementation while C++ feature parity is rebuilt.

- Language: C++
- Primary executable: C++20 compiler `numlangc`, emitting C source.
- `numlang/` is the retained Python reference compiler, not the C++ implementation.
- The C++ port currently supports a limited core subset; see `docs/cpp-compiler-status.md`.
- Default branch: main

## Working rules

- Inspect the README, manifests, CI workflows, and nearby code before editing.
- Preserve existing architecture, naming, formatting, and error-handling conventions.
- Use project scripts for validation; never claim checks you did not run.
- Keep changes scoped and update tests or documentation when behavior changes.
- Use feature branches and pull requests.
- Treat generated files, credentials, deployment configuration, and release metadata as sensitive.
- Inspect README.md, CMakeLists.txt, tests, and CI before editing.
- Keep C++ feature claims, tests, and capabilities.json synchronized.
- Fail closed for unsupported opcodes and source syntax.
- Do not claim the C++ port is feature-complete because the Python reference supports a feature.
- Keep build outputs and temporary compiler artifacts out of version control.

## Allowed agents

Only **Claude** (Anthropic) and **Mistral** (Mistral AI) may be used as coding agents in this repository. This rule supersedes any earlier agent-attribution guidance in this file.

- Agent-assisted commits must credit only one of those agents:
  - `Co-Authored-By: Claude <noreply@anthropic.com>`
  - `Co-Authored-By: Mistral Vibe <vibe@mistral.ai>`
- Allowed agent footers are `🤖 Generated with [Claude Code](https://claude.com/claude-code)` and `🤖 Generated with [Mistral Vibe](https://mistral.ai)`.
- Do not add `Co-Authored-By:` trailers, `Generated with` footers, author names, or committer identities for any other agent or AI tool.
- Do not credit another agent in commit metadata.
