#include <stdio.h>
int main(void) {
    double v0 = 1.0;
    printf("%g\n", (v0++, v0 + 10.0));
    return 0;
}
