#include <stdio.h>
int main(void) {
    double v1 = 5.0;
    double r;
    r = ++v1;
    printf("%g\n", r);
    r = v1++;
    printf("%g\n", r);
    r = v1--;
    printf("%g\n", r);
    r = --v1;
    printf("%g\n", r);
    return 0;
}
