#include <stdio.h>
int main(void) {
    printf("%g\n", (double)'A');
    printf("%g\n", (double)'\n');
    printf("%g\n", (double)'\\');
    printf("%g\n", (double)'\'');
    printf("%g\n", (double)'\x41');
    printf("%g\n", (double)'\101');
    printf("%g\n", (double)'\0');
    printf("%g\n", (double)'\?');
    printf("%g\n", (double)'\xff');
    printf("%g\n", (double)'a' + 1.0);
    return 0;
}
