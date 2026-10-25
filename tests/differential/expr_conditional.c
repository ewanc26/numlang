#include <stdio.h>
int main(void) {
    double v0 = 4.0;
    printf("%g\n", v0 > 3.0 ? v0 * 10.0 : v0 - 10.0);
    v0 = 0.0;
    double v1 = 0.0, v2 = 0.0;
    printf("%g\n", v0 != 0.0 ? (v1 = v1 + 1.0) : (v2 = v2 + 2.0));
    printf("%g\n%g\n", v1, v2);
    return 0;
}
