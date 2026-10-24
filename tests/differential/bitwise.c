#include <stdio.h>
int main(void) {
    printf("%g\n", (double)((int)12.0 & (int)10.0));
    printf("%g\n", (double)((int)12.0 | (int)10.0));
    printf("%g\n", (double)((int)12.0 ^ (int)10.0));
    printf("%g\n", (double)(~(int)12.0));
    printf("%g\n", (double)((int)1.0 << (int)4.0));
    printf("%g\n", (double)((int)-16.0 >> (int)2.0));
    return 0;
}
