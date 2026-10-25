#include <stdio.h>

int main(void) {
    printf("%g\n", 1.0);
    goto skip;
    printf("%g\n", 99.0);
skip:
    printf("%g\n", 2.0);
    goto end;
    printf("%g\n", 88.0);
end:
    printf("%g\n", 3.0);
    return 0;
}
