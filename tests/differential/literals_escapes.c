#include <stdio.h>
int main(void) {
    fputs("\x41\101\?\u00e9\U0001F600\n", stdout);
    fwrite("a\0b\n", 1, 4, stdout);
    return 0;
}
