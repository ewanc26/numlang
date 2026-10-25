#include <stdio.h>

static int n = 4;
static int d = 0;
static int perm[4] = {1, 2, 3, 4};
static int lvl[4] = {0, 0, 0, 0};
static int count = 0;
static int tmp = 0;
static int p = 0;
static int key = 0;

/* permute() for the current depth d; each leaf prints its permutation as a number. */
static void permute(void) {
    if (d == n) {
        count++;
        key = 0;
        for (p = 0; p < n; p++) {
            key = key * 10 + perm[p];
        }
        printf("%g\n", (double)key);
    } else {
        lvl[d] = d;
        while (lvl[d] < n) {
            tmp = perm[d];
            perm[d] = perm[lvl[d]];
            perm[lvl[d]] = tmp;
            d = d + 1;
            permute();
            d = d - 1;
            tmp = perm[d];
            perm[d] = perm[lvl[d]];
            perm[lvl[d]] = tmp;
            lvl[d] = lvl[d] + 1;
        }
    }
}

int main(void) {
    d = 0;
    permute();
    printf("%g\n", (double)count);
    return 0;
}
