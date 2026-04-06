# Numlang compiler

Numlang is an esoteric stack-based language using only the characters `0123456789^&*+-+/.|;`.

## Features

- Stack-based operations
- Numbers 0-9 push literals to stack
- |n pushes the value of variable n (0-9)
- & assigns: value |n & assigns the popped value to variable n
- + : add
- - : subtract
- * : multiply
- / : divide
- ^ : power
- | : bitwise or (when not followed by digit)
- . : print top of stack
- ; : ignored

## Example

```
5|0&|0.
```

Assigns 5 to var 0, pushes var 0, prints 5.