#include <stdio.h>
int main(void) {
    double v0 = 3.0;
    while (v0 > 0.0) {
        printf("%g\n", v0);
        v0 = v0 - 1.0;
    }
    return 0;
}
