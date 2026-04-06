# Numlang compiler

Numlang is an esoteric stack-based language using only the characters `0123456789^&*+-+/.|;`.

## Features

- Stack-based operations
- Numbers: push literals
- |n : push variable n (0-9)
- & : assign value to variable
- + : add
- - : subtract
- * : multiply
- / : divide
- ^ : read double from input
- 10 : <
- 11 : >
- 12 : ==
- 13 : !=
- 14 : <=
- 15 : >=
- | : print top of stack
- .n : call function n
- /n code ; : define function n
- ; : ignored

## Example

```
/0 5|0&|0 ;  .0
```

Defines function 0 that assigns 5 to var 0 and prints it, then calls it.