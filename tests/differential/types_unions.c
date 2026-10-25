#include <stdio.h>

union Num { int i; double d; };

int main(void) {
    union Num u;
    u.d = 2.5;
    printf("%g\n", u.d);
    union Num v;
    v.i = 7;
    printf("%g\n", (double)v.i);
    printf("%g\n", (double)sizeof(union Num));
    return 0;
}
