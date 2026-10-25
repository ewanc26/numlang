#include <stdio.h>
#include <stdlib.h>

static double stk[64];
static int sp = 0;

static void push(double x) { stk[sp++] = x; }
static double pop(void) { return stk[--sp]; }

static void add(void) { double b = pop(); double a = pop(); push(a + b); }
static void sub(void) { double b = pop(); double a = pop(); push(a - b); }
static void mul(void) { double b = pop(); double a = pop(); push(a * b); }
static void dvd(void) {
    double b = pop();
    double a = pop();
    if (b == 0.0) {
        printf("division by zero\n");
        exit(3);
    }
    push(a / b);
}

/* Token codes 1-4 select an operation; 100+v pushes v; 0 ends an expression. */
static int tok[18] = {106, 102, 1, 103, 3, 108, 104, 4, 2, 0,
                      105, 101, 2, 0,
                      107, 100, 4, 0};
static int pc = 0;
static int ops = 0;
static void (*op)(void);

static void eval(void) {
    while (tok[pc] != 0) {
        switch (tok[pc]) {
        case 1: op = add; op(); ops = ops + 1; break;
        case 2: op = sub; op(); ops = ops + 1; break;
        case 3: op = mul; op(); ops = ops + 1; break;
        case 4: op = dvd; op(); ops = ops + 1; break;
        default: push((double)(tok[pc] - 100)); break;
        }
        pc = pc + 1;
    }
}

int main(void) {
    pc = 0;
    eval();
    printf("%g\n", pop());
    pc = 10;
    eval();
    printf("%g\n", pop());
    printf("%g\n", (double)ops);
    pc = 14;
    eval();
    printf("%g\n", pop());
    printf("not reached\n");
    return 0;
}
