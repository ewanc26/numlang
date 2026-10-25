#include <stdio.h>

struct Pt { int x; int y; };

int main(void) {
    int a[4] = {1, 2};
    printf("%g\n", (double)a[1]);
    printf("%g\n", (double)a[3]);
    struct Pt p = {.y = 5};
    printf("%g\n", (double)p.x);
    printf("%g\n", (double)p.y);
    struct Pt q = {7, 8};
    printf("%g\n", (double)q.y);
    int m[2][2] = {{1, 2}, {3, 4}};
    printf("%g\n", (double)m[1][0]);
    static int s = 6;
    printf("%g\n", (double)s);
    return 0;
}
