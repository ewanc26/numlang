#include <stdio.h>
int main(void) {
    for (int i = 0; i < 10; i++) {
        if (i == 2) continue;
        if (i == 6) break;
        printf("%g\n", (double)i);
    }
    double v0 = 0.0;
    while (v0 < 100.0) {
        v0 = v0 + 1.0;
        if (v0 == 2.0) continue;
        if (v0 == 5.0) break;
        printf("%g\n", v0);
    }
    return 0;
}
