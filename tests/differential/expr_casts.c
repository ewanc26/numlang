#include <stdio.h>
int main(void) {
    printf("%g\n", (double)(int)3.9);
    printf("%g\n", (double)(int)-3.9);
    printf("%g\n", (double)(signed char)65.7);
    printf("%g\n", (double)(_Bool)3.5);
    printf("%g\n", (double)(_Bool)0.0);
    return 0;
}
