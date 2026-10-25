#include <stdio.h>

int arr[3] = {1, 2, 3};
int *fp = arr;

struct P {
    int a[2];
    int b;
};
struct P s = {{5, 6}, 7};
int *m = s.a;

static void f0(void) {
    static int sarr[2] = {8, 9};
    static int *sp = sarr;
    printf("%g\n", (double)sp[1]);
    int local[3] = {4, 5, 6};
    int *lp = local;
    printf("%g\n", (double)lp[2]);
}

int main(void) {
    fp[2] = 7;
    printf("%g\n", (double)arr[2]);
    int *q;
    q = arr;
    printf("%g\n", (double)q[0]);
    printf("%g\n", (double)m[1]);
    q = s.a;
    printf("%g\n", (double)q[0]);
    f0();
    int mine[2] = {10, 11};
    q = mine;
    printf("%g\n", (double)q[1]);
    return 0;
}
