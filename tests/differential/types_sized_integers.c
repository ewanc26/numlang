#include <stdio.h>
int main(void) {
    printf("%g\n", (double)(unsigned char)300);
    printf("%g\n", (double)(signed char)200);
    printf("%g\n", (double)(unsigned int)(0 - 1));
    printf("%g\n", (double)(unsigned short)(0 - 1));
    printf("%g\n", (double)(short)70000);
    printf("%g\n", (double)(unsigned char)(200 + 100));
    printf("%g\n", (double)(unsigned long long)(0 - 1));
    printf("%g\n", (double)(int)2147483648LL);
    printf("%g\n", (double)(signed char)(129 - 1 - 0));
    return 0;
}
