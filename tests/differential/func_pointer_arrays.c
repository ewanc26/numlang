#include <stdio.h>

static double f0(double x) {
    return x * 2.0;
}

static double f1(double x) {
    return x * 3.0;
}

static double f2(double x) {
    return x + 1.0;
}

int main(void) {
    double (*table[3])(double) = {f0, f1, f2};
    printf("%g\n", table[0](5.0));
    printf("%g\n", table[1](5.0));
    printf("%g\n", table[2](5.0));
    double (*slots[2])(double);
    slots[0] = table[2];
    slots[1] = f1;
    printf("%g\n", slots[0](9.0));
    printf("%g\n", slots[1](9.0));
    double (*sized[])(double) = {f1, f0};
    printf("%g\n", (double)sizeof(sized));
    int k = 1;
    printf("%g\n", table[k](9.0));
    return 0;
}
