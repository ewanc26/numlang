#include <stdio.h>
static double f0(double x) { return x * 2.0; }
static double f1(double x) { return x * x; }
int main(void) {
    printf("%g\n", f0(3.0));
    printf("%g\n", f1(4.0));
    return 0;
}
