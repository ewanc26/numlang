#include <stdio.h>

int main(void) {
    int a = -7;
    int b = 2;
    printf("%g\n", (double)(a / b));
    printf("%g\n", (double)(a % b));
    printf("%g\n", (double)(3 == 3));
    printf("%g\n", (double)(3 == 4));
    return 0;
}
