#include <stdio.h>

int main(void) {
    const int limit = 10;
    printf("%g\n", (double)limit);
    volatile int flag = 1;
    printf("%g\n", (double)flag);
    int v = 3;
    int *restrict rp = &v;
    rp[0] = rp[0] + 2;
    printf("%g\n", (double)v);
    const int *cp = &v;
    printf("%g\n", (double)cp[0]);
    int *const fixed = &v;
    printf("%g\n", (double)fixed[0]);
    static int calls = 0;
    printf("%g\n", (double)calls);
    return 0;
}
