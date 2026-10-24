#include <stdio.h>

int main(void) {
    int arr[5] = {0};
    arr[2] = 7;
    printf("%g\n", (double)arr[2]);
    for (int i = 0; i < 5; i++) {
        arr[i] = i * i;
    }
    for (int i = 0; i < 5; i++) {
        printf("%g\n", (double)arr[i]);
    }
    return 0;
}
