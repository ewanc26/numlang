# Numlang compiler

Numlang is an esoteric stack-based language that compiles to C via a Python compiler.
The character set is `0-9 ^ & * + - / . | ; % # ~ \" !`.

> 🧶 Also available on [Tangled](https://tangled.org/ewancroft.uk/numlang)

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

# Increase the runtime stack depth (default 1000)
numlangc hello.num --run --stack-size 4096

# Debug: dump the token stream
numlangc hello.num --emit-tokens

# Debug: dump the parsed AST
numlangc hello.num --emit-ast
```

---

## Language reference

### Data model

- All values are 64-bit IEEE 754 doubles.
- The runtime has a stack (depth configurable, default 1000) and **100 named variables** `vars[0]`–`vars[99]`, all initialised to `0`.

### Comments

`# text` — ignored to end of line.

---

### Pushing values

| Syntax | Effect |
|--------|--------|
| `N` (integer literal) | Push the integer N, **unless** N is a special opcode (see tables below) |
| `N.M` (float literal) | Push the floating-point value N.M — **never** treated as an opcode |
| `\|n` or `\|nn` | Push the value of variable n (0–99) |

> **Tip:** If you need to push the raw number 10 (which is also the `LT` opcode), use the float form `10.0`.

---

### Stack manipulation

| Code | Name | Effect |
|------|------|--------|
| `16` | DUP  | Duplicate top of stack |
| `17` | SWAP | Swap top two elements |
| `18` | DROP | Discard top of stack |

---

### Arithmetic

| Symbol | Effect |
|--------|--------|
| `+` | pop b, pop a → push a + b |
| `-` | pop b, pop a → push a − b |
| `*` | pop b, pop a → push a × b |
| `/` | pop b, pop a → push a ÷ b (runtime error if b == 0) |
| `%` | pop b, pop a → push `fmod(a, b)` (runtime error if b == 0) |
| `38` | IMOD — integer remainder: `(int)a % (int)b` |

---

### Comparison  *(push 1.0 = true, 0.0 = false)*

| Code | Meaning |
|------|---------|
| `10` | a < b |
| `11` | a > b |
| `12` | a == b |
| `13` | a != b |
| `14` | a <= b |
| `15` | a >= b |

---

### Logical operators

| Syntax | Effect |
|--------|--------|
| `!`    | **NOT** — pop x; push 1 if x == 0, else push 0 |
| `19`   | **OR** — pop b, pop a; push 1 if either non-zero, else 0 |
| `39`   | **AND** — pop b, pop a; push 1 if both non-zero, else 0 |

---

### Bitwise operators *(operands truncated to `int` before the operation)*

| Code | Name | Effect |
|------|------|--------|
| `40` | BAND | `(int)a & (int)b` |
| `41` | BOR  | `(int)a \| (int)b` |
| `42` | BXOR | `(int)a ^ (int)b` |
| `43` | BNOT | `~(int)a` (unary) |
| `44` | BSHL | `(int)a << (int)b` |
| `45` | BSHR | `(int)a >> (int)b` (arithmetic) |

---

### Math built-ins

| Code | Name   | Effect |
|------|--------|--------|
| `21` | ABS    | pop x → push \|x\| |
| `22` | SQRT   | pop x → push √x (runtime error if x < 0) |
| `23` | FLOOR  | pop x → push ⌊x⌋ |
| `24` | CEIL   | pop x → push ⌈x⌉ |
| `25` | NEG    | pop x → push −x |
| `26` | MIN2   | pop b, pop a → push min(a, b) |
| `27` | MAX2   | pop b, pop a → push max(a, b) |
| `29` | POW    | pop exp, pop base → push base^exp |
| `31` | LOG    | pop x → push ln(x) (runtime error if x ≤ 0) |
| `32` | LOG10  | pop x → push log₁₀(x) (runtime error if x ≤ 0) |
| `33` | SIN    | pop x (radians) → push sin(x) |
| `34` | COS    | pop x (radians) → push cos(x) |
| `35` | TAN    | pop x (radians) → push tan(x) |
| `46` | ASIN   | pop x → push arcsin(x) in radians (domain error if x ∉ [−1, 1]) |
| `47` | ACOS   | pop x → push arccos(x) in radians (domain error if x ∉ [−1, 1]) |
| `48` | ATAN   | pop x → push arctan(x) in radians |
| `49` | ATAN2  | pop x, pop y → push atan2(y, x) in radians |
| `36` | ROUND  | pop x → push nearest integer (halfway rounds away from zero) |
| `37` | TRUNC  | pop x → push integer part, truncated toward zero |

---

### Misc operations

| Code | Name | Effect |
|------|------|--------|
| `60` | RAND | push a random double in [0, 1) |
| `61` | TIME | push current Unix timestamp as a double |
| `62` | EXIT | pop exit code; terminate program immediately |
| `63` | DEPTH | push the current stack depth as a double |
| `64` | PICK  | pop n; push a copy of the element n positions below the (new) top (0 = top) |

---

### Control flow

#### IF / IF-ELSE  (block form)

```
<condition>
20
    <then_body>
[28
    <else_body>]
;
```

Pops the condition from the stack. If non-zero, executes `then_body`; otherwise executes the optional `else_body`.  
The `then_body` and `else_body` may each contain arbitrarily many operations, including nested control flow.

> The integer `28` acts as the **else-separator** *only* when it appears at the top level inside an `IF` block.  Anywhere else — including nested inside a `WHILE` or `REPEAT` body — `28` is a plain numeric push.

#### WHILE

```
<initial_condition>
30
    <body>
    <next_condition>
;
```

Pops the condition before each iteration. Runs the body while the condition is non-zero.  
The body is responsible for leaving the next condition on the stack.

#### REPEAT

```
<count>
50
    <body>
;
```

Pops `count`, then executes `body` exactly `count` times.  
Before each iteration, the **0-based iteration index** is pushed onto the stack for the body to use. Use `18` (DROP) to discard it if you don't need it.

---

### Variables

```
<value> <index> &
```

Pops the index (0–99), then the value, and stores `vars[index] = value`.

```
|n   # push vars[n], single digit (0–9)
|nn  # push vars[nn], two digits (10–99)
```

Example — store π in var 10 and retrieve it:

```
3.14159 10 &
|10 |
```

---

### I/O

| Symbol | Effect |
|--------|--------|
| `\|`   | Pop and print top of stack as a number (followed by newline) |
| `~`    | Pop and print top of stack as an ASCII character (no newline) |
| `^`    | Read a double from stdin and push it |
| `"..."` | Print a string literal (see below) |

---

### String literals

`"..."` prints each character in the string immediately — the multi-character
sibling of `~`. It desugars to a `putchar()` call per character and leaves
the stack unchanged.

Escape sequences follow the full C syntax set:

| Escape | Value | Meaning |
|--------|-------|---------|
| `\n`   | 10    | newline |
| `\t`   | 9     | horizontal tab |
| `\r`   | 13    | carriage return |
| `\\`   | 92    | backslash |
| `\"`   | 34    | double quote |
| `\'`   | 39    | single quote |
| `\a`   | 7     | alert / bell |
| `\b`   | 8     | backspace |
| `\f`   | 12    | form feed |
| `\v`   | 11    | vertical tab |
| `\xHH` | 0–255 | hex escape (1–2 hex digits) |
| `\NNN` | 0–255 | octal escape (1–3 octal digits, first digit 0–7) |

---

### Functions

```
/N  <body>  ;   # define function N
.N              # call function N
```

Function numbers are plain integers (0, 1, 2, …).
Functions may be defined in any order; forward calls are supported.
Recursion is supported.

> **Warning:** The `/` character is both the division operator **and** the function definition prefix. When `/` is followed by an integer literal, it is parsed as a function definition. For example, `4 / 0 &` will define function 0 instead of dividing 4 by 0. Use `4.0 / 0 &` or restructure your code to avoid this ambiguity.

---

## Gotchas and tips

1. **Opcode collisions**: Integer literals that match opcode numbers are interpreted as opcodes, not values. Use float syntax (e.g., `10.0` instead of `10`) to push these numbers. Affected numbers: 10–15 (comparisons), 16–18 (stack), 19 (OR), 20 (IF), 21–27 (math), 28 (ELSE), 29 (POW), 30 (WHILE), 31–35 (trig), 36–39 (round/logical), 40–45 (bitwise), 46–49 (inverse trig), 50 (REPEAT), 60–64 (misc).

2. **Division vs functions**: `/` followed by an integer defines a function. Use float divisors or pre-compute values to avoid this.

3. **String literals**: All characters in strings are output as raw byte values via `putchar()`. Non-ASCII characters may cause encoding issues on some systems.

---

## Full opcode reference

| Code(s)  | Name(s)         | Category    |
|----------|-----------------|-------------|
| `16`     | DUP             | Stack       |
| `17`     | SWAP            | Stack       |
| `18`     | DROP            | Stack       |
| `10`     | LT              | Compare     |
| `11`     | GT              | Compare     |
| `12`     | EQ              | Compare     |
| `13`     | NE              | Compare     |
| `14`     | LE              | Compare     |
| `15`     | GE              | Compare     |
| `!`      | NOT             | Logical     |
| `19`     | OR              | Logical     |
| `39`     | AND             | Logical     |
| `40`     | BAND            | Bitwise     |
| `41`     | BOR             | Bitwise     |
| `42`     | BXOR            | Bitwise     |
| `43`     | BNOT            | Bitwise     |
| `44`     | BSHL            | Bitwise     |
| `45`     | BSHR            | Bitwise     |
| `21`     | ABS             | Math        |
| `22`     | SQRT            | Math        |
| `23`     | FLOOR           | Math        |
| `24`     | CEIL            | Math        |
| `25`     | NEG             | Math        |
| `26`     | MIN2            | Math        |
| `27`     | MAX2            | Math        |
| `29`     | POW             | Math        |
| `31`     | LOG             | Math        |
| `32`     | LOG10           | Math        |
| `33`     | SIN             | Math        |
| `34`     | COS             | Math        |
| `35`     | TAN             | Math        |
| `46`     | ASIN            | Math        |
| `47`     | ACOS            | Math        |
| `48`     | ATAN            | Math        |
| `49`     | ATAN2           | Math        |
| `36`     | ROUND           | Math        |
| `37`     | TRUNC           | Math        |
| `38`     | IMOD            | Math        |
| `20`     | IF (block)      | Control     |
| `28`     | ELSE separator  | Control     |
| `30`     | WHILE           | Control     |
| `50`     | REPEAT          | Control     |
| `60`     | RAND            | Misc        |
| `61`     | TIME            | Misc        |
| `62`     | EXIT            | Misc        |
| `63`     | DEPTH           | Misc        |
| `64`     | PICK            | Misc        |

---

## Examples

### Hello, World!

```
"Hello, World!\n"
```

### Assign and print

```
99 0 &      # vars[0] = 99
|0 |        # print vars[0]
```

### Float literals

```
3.14159 0 &     # push π, store in vars[0]
2.71828 1 &     # push e, store in vars[1]
|0 |            # print π
|1 31 |         # print ln(e) ≈ 1
2 10 29 |       # print 2^10 = 1024
```

### Block-form IF with ELSE

```
7 5 11          # push (7 > 5) = 1
20
    "7 is greater than 5\n"
28
    "7 is not greater than 5\n"
;
```

### Nested IF-ELSE (FizzBuzz logic)

```
|0 15 38 0 12   # (n % 15) == 0
20
    "FizzBuzz\n"
28
    |0 3 38 0 12    # (n % 3) == 0
    20
        "Fizz\n"
    28
        "Buzz\n"    # simplified; real fizzbuzz also checks %5
    ;
;
```

### WHILE countdown

```
5 0 &               # vars[0] = 5
|0 0 11             # initial condition: vars[0] > 0
30
    |0 |            # print vars[0]
    |0 1 - 0 &      # vars[0] -= 1
    |0 0 11         # next condition
;
```

### REPEAT loop (print 0 to 4)

```
5 50
    |               # print iteration index
;
```

### Bitwise masking

```
255 15 40 |         # 255 AND 15 = 15 (lower nibble)
1 8 44  |           # 1 << 8 = 256
```

### Functions

```
/0
    "Hello from function 0!\n"
;

.0
```

### Recursion — power of 2

```
# Function 0: push 2^vars[0]
# Uses iterative doubling via WHILE
/0
    1 1 &           # vars[1] = result = 1
    |0 0 11         # condition: vars[0] > 0
    30
        |1 2 * 1 &  # result *= 2
        |0 1 - 0 &  # vars[0] -= 1
        |0 0 11
    ;
    |1 |
;

10 0 &   # vars[0] = exponent
.0       # prints 1024
```

---

## Project layout

```
numlang/
  lexer.py      — tokeniser (float literals, |nn variables)
  parser.py     — recursive-descent parser → AST
  ast.py        — AST node types
  sema.py       — semantic analysis
  codegen_c.py  — C code generator
  main.py       — CLI entry point
examples/
  hello.num
  hello_world.num
  compare.num
  if.num          — block IF / IF-ELSE / nested IF
  while.num
  repeat.num      — REPEAT loop with iteration index
  function.num
  fizzbuzz.num    — uses nested IF-ELSE
  factorial.num
  floats.num      — float literals and math built-ins
  trig.num        — sin, cos, tan, asin, acos, atan, atan2
  stack_introspect.num — DEPTH and PICK
  bitwise.num     — BAND, BOR, BXOR, BNOT, BSHL, BSHR
  logical.num     — NOT, OR, AND
  math_ops.num
  complex.num     — statistics calculator + Collatz sequence
  stack.num
  strings.num
  input.num
  modulo.num
```
