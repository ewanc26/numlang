#include <stdio.h>

struct Point { int x; int y; };

int main(void) {
    struct Point p;
    p.x = 3;
    p.y = 4;
    struct Point *q = &p;
    q->x = q->x + 10;
    printf("%g\n", (double)p.x);
    printf("%g\n", (double)p.y);
    struct Point r;
    r = p;
    printf("%g\n", (double)r.y);
    printf("%g\n", (double)sizeof(struct Point));
    return 0;
}
