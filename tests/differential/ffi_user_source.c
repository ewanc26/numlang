#include <stdio.h>

#include "ffi_user_helper.c"

int main(void) {
    printf("%g\n", scalek(3.0, 4.0));
    return 0;
}
