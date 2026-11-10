#include <cstddef>
#include <cstdint>

extern "C" {
volatile uint64_t tohost __attribute__((section(".tohost"), aligned(64)));
volatile uint64_t fromhost __attribute__((section(".tohost"), aligned(64)));
char test_log[8192];
static size_t used;
void test_text(const char *s) {
    while (*s && used + 1 < sizeof(test_log)) test_log[used++] = *s++;
}
void test_number(uint64_t x) {
    char text[21]; unsigned n = 0;
    do { text[n++] = '0' + x % 10; x /= 10; } while (x);
    while (n) { char s[2] = {text[--n], 0}; test_text(s); }
}
void *memcpy(void *dst, const void *src, size_t n) {
    auto *d = static_cast<unsigned char *>(dst);
    auto *s = static_cast<const unsigned char *>(src);
    for (size_t i = 0; i < n; ++i) d[i] = s[i];
    return dst;
}
void *memset(void *dst, int byte, size_t n) {
    auto *d = static_cast<unsigned char *>(dst);
    for (size_t i = 0; i < n; ++i) d[i] = byte;
    return dst;
}
int memcmp(const void *a, const void *b, size_t n) {
    auto *x = static_cast<const unsigned char *>(a);
    auto *y = static_cast<const unsigned char *>(b);
    for (size_t i = 0; i < n; ++i) if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
    return 0;
}
void test_trap(uint64_t cause, uint64_t pc, uint64_t value) {
    test_text("TRAP cause="); test_number(cause);
    test_text(" pc="); test_number(pc); test_text(" value="); test_number(value); test_text("\n");
}
}
