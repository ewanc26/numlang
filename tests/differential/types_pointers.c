#include <stdio.h>

int main(void) {
    int a = 3;
    int *p = &a;
    p[0] = p[0] + 4;
    printf("%g\n", (double)a);
    int **pp = &p;
    pp[0][0] = 9;
    printf("%g\n", (double)a);
    int arr[3] = {1, 2, 3};
    int *e = &arr[1];
    printf("%g\n", (double)e[0]);
    printf("%g\n", (double)e[1]);
    return 0;
}
