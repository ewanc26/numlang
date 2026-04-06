# Numlang compiler

Numlang is an esoteric stack-based language that compiles to C via a Python compiler.
The character set is `0-9 ^ & * + - / . | ; % #`.

---

## Installation

```sh
pip install -e .
```

This installs the `numlangc` command.

---

## Usage

```sh
# Compile to a C file
numlangc hello.num -o hello.c

# Compile, run with gcc, and execute immediately
numlangc hello.num --run

# Use a different C compiler
numlangc hello.num --run --cc clang
```

---

## Language reference

### Data model

- All values are 64-bit IEEE 754 doubles.
- The runtime has a stack (depth 1000) and 10 named variables `vars[0]` – `vars[9]`, all initialised to `0`.

### Comments

`# text` — ignored to end of line.

### Pushing values

| Syntax | Effect |
|--------|--------|
| `N` (integer literal) | Push the number N |
| `\|n` | Push the value of variable n (0–9) |

### Stack manipulation

| Code | Name | Effect |
|------|------|--------|
| `16` | DUP  | Duplicate top of stack |
| `17` | SWAP | Swap top two elements |
| `18` | DROP | Discard top of stack |

### Arithmetic & modulo

| Symbol | Effect |
|--------|--------|
| `+` | pop b, pop a → push a + b |
| `-` | pop b, pop a → push a − b |
| `*` | pop b, pop a → push a × b |
| `/` | pop b, pop a → push a ÷ b |
| `%` | pop b, pop a → push a mod b (via `fmod`) |

### Comparison (push 1.0 = true, 0.0 = false)

| Code | Meaning |
|------|---------|
| `10` | a < b |
| `11` | a > b |
| `12` | a == b |
| `13` | a != b |
| `14` | a <= b |
| `15` | a >= b |

### Control flow

| Syntax | Effect |
|--------|--------|
| `20` | **IF** — pops condition; if non-zero, executes the **next single** operation |
| `30 … ;` | **WHILE** — pops condition each iteration; executes the body if non-zero; body must leave next condition on stack |

### Variables

```
<value> <index> &
```

Pops the index (0–9), then the value, and stores `vars[index] = value`.

Example — store 42 in var 3:
```
42 3 &
```

### I/O

| Symbol | Effect |
|--------|--------|
| `\|` | Pop and print top of stack (followed by newline) |
| `^` | Read a double from stdin and push it |

### Functions

```
/N  <body>  ;   # define function N
.N              # call function N
```

Function numbers are plain integers (0, 1, 2, …).  
Functions may be defined in any order; forward calls are supported.

---

## Examples

### Hello, World!

```
42 |
```

### Assign and print

```
99 0 &      # vars[0] = 99
|0 |        # print vars[0]
```

### Countdown with WHILE

```
5 0 &               # vars[0] = 5
|0 0 11             # initial condition: vars[0] > 0
30
    |0 |            # print vars[0]
    |0 1 - 0 &      # vars[0] -= 1
    |0 0 11         # next condition
;
```

Output: `5 4 3 2 1`

### Functions

```
/0
    5 0 &
    |0 |
;

.0
```

### Conditional (IF)

```
3 5 10          # push (3 < 5) = 1
20 99 |         # IF true: print 99
```

---

## Project layout

```
numlang/
  lexer.py      – tokeniser
  parser.py     – recursive-descent parser → AST
  ast.py        – AST node types
  sema.py       – semantic analysis (undefined calls, malformed control flow)
  codegen_c.py  – C code generator
  main.py       – CLI entry point
examples/       – sample .num programs
```
