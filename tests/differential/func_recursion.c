#include <stdio.h>
static double fact(double n) { return n < 2.0 ? 1.0 : n * fact(n - 1.0); }
int main(void) {
    printf("%g\n", fact(5.0));
    printf("%g\n", fact(10.0));
    printf("%g\n", fact(0.0));
    return 0;
}
