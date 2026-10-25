#include <stdio.h>

enum Color { RED, GREEN = 5, BLUE };

int main(void) {
    enum Color c = GREEN;
    printf("%g\n", (double)c);
    printf("%g\n", (double)BLUE);
    printf("%g\n", (double)RED);
    printf("%g\n", (double)sizeof(enum Color));
    return 0;
}
