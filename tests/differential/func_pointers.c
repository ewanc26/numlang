#include <stdio.h>

static double twice(double x) {
    return x * 2.0;
}

int main(void) {
    double (*fp)(double) = twice;
    printf("%g\n", fp(5.0));
    double (*other)(double) = fp;
    printf("%g\n", other(7.0));
    return 0;
}
