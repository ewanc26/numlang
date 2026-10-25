#include <stdio.h>

typedef double Real;
typedef int Count;
typedef Count *CountPtr;

int main(void) {
    Real r = 2.5;
    Count n = 7;
    printf("%g\n", r);
    printf("%g\n", (double)n);
    Count m = 3;
    CountPtr p = &m;
    p[0] = p[0] * 2;
    printf("%g\n", (double)m);
    return 0;
}
