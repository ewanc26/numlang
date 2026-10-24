#include <stdio.h>
int main(void) {
    printf("%g\n", (double)((1.0 != 0.0) && (0.0 != 0.0)));
    printf("%g\n", (double)((1.0 != 0.0) || (0.0 != 0.0)));
    printf("%g\n", (double)((0.0 != 0.0) || (0.0 != 0.0)));
    printf("%g\n", (double)(0.0 == 0.0));
    printf("%g\n", (double)(3.0 < 4.0));
    printf("%g\n", (double)(4.0 == 4.0));
    return 0;
}
