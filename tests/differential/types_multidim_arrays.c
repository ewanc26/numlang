#include <stdio.h>

int main(void) {
    int grid[2][3] = {{0}};
    grid[1][2] = 6;
    grid[0][0] = 1;
    printf("%g\n", (double)grid[1][2]);
    printf("%g\n", (double)grid[0][0]);
    printf("%g\n", (double)sizeof(grid));
    int *row = grid[1];
    printf("%g\n", (double)row[2]);
    int cube[2][2][2] = {{{1}, {2, 3}}, {{4}}};
    printf("%g\n", (double)cube[0][1][0]);
    printf("%g\n", (double)cube[1][0][0]);
    printf("%g\n", (double)cube[1][1][1]);
    return 0;
}
