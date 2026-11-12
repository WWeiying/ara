#include <stdint.h>
#include <stddef.h>

extern void _putchar(char);
void test_text(const char *s) { while (*s) _putchar(*s++); }
void test_number(uint64_t x) {
    char text[21]; unsigned n = 0;
    do { text[n++] = '0' + x % 10; x /= 10; } while (x);
    while (n) _putchar(text[--n]);
}
void test_exit(unsigned code) {
    register uint64_t value __asm__("a0") = code;
    __asm__ volatile("j _eoc" :: "r"(value) : "memory");
    __builtin_unreachable();
}
