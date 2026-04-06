#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define STACK_SIZE 1000

double stack[STACK_SIZE];
int sp = 0;
double vars[10] = {0};

void push(double x) {
    if (sp >= STACK_SIZE) {
        fprintf(stderr, "Stack overflow\n");
        exit(1);
    }
    stack[sp++] = x;
}

double pop() {
    if (sp <= 0) {
        fprintf(stderr, "Stack underflow\n");
        exit(1);
    }
    return stack[--sp];
}

void func_0() {
    push(5.0);
    push(vars[0]);
    { int var = (int)pop(); double val = pop(); vars[var] = val; }
    push(vars[0]);
    printf("%g\n", pop());
}

int main() {
    func_0();
    return 0;
}