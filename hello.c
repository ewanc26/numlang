#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define STACK_SIZE 1000

double stack[STACK_SIZE];
int sp = 0;

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

int main() {
    push(2.0);
    push(3.0);
    { double b = pop(); double a = pop(); push(a + b); }
    printf("%g\n", pop());
    return 0;
}