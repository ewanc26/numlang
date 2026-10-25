#include <stdio.h>
int main(void) {
    printf("%g\n", (double)0x1F);
    printf("%g\n", (double)017);
    printf("%g\n", (double)0b101);
    printf("%g\n", (double)10u);
    printf("%g\n", (double)0XffUL);
    printf("%g\n", (double)0xFFFFFFFF);
    printf("%g\n", (double)0);
    return 0;
}
