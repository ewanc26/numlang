#include <stdio.h>
int main(void) {
    double v0 = 0.0;
    do {
        printf("%g\n", v0);
        v0 = v0 + 1.0;
    } while (v0 < 3.0);
    double v1 = 5.0;
    do {
        printf("%g\n", v1);
        v1 = v1 + 1.0;
    } while (v1 < 3.0);
    return 0;
}
