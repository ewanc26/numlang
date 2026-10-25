#include <stdio.h>

int main(void) {
    switch ((long long)2) {
    case 1: printf("%g\n", 10.0); break;
    case 2: printf("%g\n", 20.0); break;
    default: printf("%g\n", 30.0); break;
    }
    switch ((long long)9) {
    case 1: printf("%g\n", 1.0); break;
    default: printf("%g\n", 99.0); break;
    }
    switch ((long long)1) {
    case 1: printf("%g\n", 11.0);
    case 2: printf("%g\n", 22.0); break;
    }
    return 0;
}
