#include <stdio.h>

struct Mixed { char c; double d; };

int main(void) {
    printf("%g\n", (double)sizeof(char));
    printf("%g\n", (double)sizeof(int));
    printf("%g\n", (double)sizeof(double));
    printf("%g\n", (double)sizeof(struct Mixed));
    int arr[5];
    printf("%g\n", (double)sizeof(arr));
    return 0;
}
