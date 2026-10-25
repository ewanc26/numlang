#include <stdio.h>

struct Rec {
    int key;
    int val;
};

int main(void) {
    struct Rec tbl[6] = {{42, 1}, {7, 2}, {19, 3}, {88, 4}, {3, 5}, {19, 6}};
    /* Insertion sort by key; the strict comparison keeps equal keys in input order. */
    for (int i = 1; i < 6; i++) {
        struct Rec tmp = tbl[i];
        int j = i;
        while (j > 0 && tbl[j - 1].key > tmp.key) {
            tbl[j] = tbl[j - 1];
            j = j - 1;
        }
        tbl[j] = tmp;
    }
    for (int k = 0; k < 6; k++) {
        printf("%g\n", (double)tbl[k].key);
        printf("%g\n", (double)tbl[k].val);
    }
    return 0;
}
