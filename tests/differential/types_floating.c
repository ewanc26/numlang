#include <stdio.h>
int main(void) {
    float a = 16777217.0;
    printf("%g\n", (double)(a - 16777216.0));
    printf("%g\n", (double)((float)0.1 - 0.1));
    printf("%g\n", (double)(double)(float)0.1);
    float third = 1.0f / 3.0f;
    printf("%g\n", (double)(third * 3.0f));
    return 0;
}
