/* Host-only input and original-oracle checks; never linked into target ELFs. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#if SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
#include "inputs.h"
extern int CASE_MAIN(void);
static unsigned mutation, calls;

long replay_write(long n, long fd, long p, long len) {
    if (n != 64 || fd != 1 || len < 0) abort();
    return (long)fwrite((const void *)p, 1, (size_t)len, stdout);
}
unsigned long capacity(void) { return CAP; }
static uint64_t hash_bytes(uint64_t h, const void *p, size_t n) {
    const uint8_t *b = p;
    for (size_t i = 0; i < n; ++i) h = (h ^ b[i]) * UINT64_C(1099511628211);
    return h;
}
#define ARGS const void *a, const void *s, void *d, unsigned long vl, \
    unsigned long cap, const void *m, unsigned long control, void *result
#define PASS_ARGS a, s, d, vl, cap, m, control, result
static unsigned long model(unsigned op, ARGS) {
    const word *src = a;
    word *dst = d;
    uint64_t scalar = *(const uint64_t *)s;
#if SEW == 64
    uint64_t boxed_zero = 0;
#else
    uint64_t boxed_zero = UINT64_MAX << SEW;
#endif
    if (++calls != 1 || op != ORIGINAL_OP || cap != CAP || vl != 2 || control != 1 ||
        scalar != boxed_zero || *(uint64_t *)result != UINT64_C(0x123456789abcdef0)) abort();
    for (unsigned i = 0; i < cap; ++i)
        if (src[i] != inputs[i % 16] || dst[i] != inputs[(3*i+11) % 16]) abort();
    for (unsigned i = 0; i < 128; ++i) if (((const uint8_t *)m)[i] != 255) abort();
    if (dst[-1] != 0x5b || dst[cap] != 0x5b) abort();
    uint64_t h = hash_bytes(UINT64_C(14695981039346656037), a, cap*sizeof(word));
    h = hash_bytes(h, d, cap*sizeof(word));
    h = hash_bytes(h, m, 128);
    h = hash_bytes(h, s, 8);
    printf("HOST_CALL op=%u cap=%lu vl=%lu vstart=%lu input_hash=%016llx\n",
           op, cap, vl, control, (unsigned long long)h);
    /* All archived cases have VL2/start1; execute only the architectural body. */
    if (op == 6) dst[0] = (word)scalar;
    else if (op == 2 || op == 4) dst[1] = src[0];
    else if (op == 3 || op == 5) dst[1] = (word)scalar;
    else abort();
    if (mutation == 1) dst[0] = op == 6 ? inputs[11] : (op == 2 || op == 4) ? inputs[0] : inputs[1];
    if (mutation == 2) dst[cap-1] ^= 1;
    if (mutation == 3) return UINT64_C(16) << 32;
    if (mutation == 4) dst[-1] ^= 1;
    if (mutation == 5) return 1;
    if (mutation == 6) *(uint64_t *)result ^= 1;
    return 0;
}
#define OP(n) unsigned long op_##n(ARGS) { return model(n, PASS_ARGS); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7)
int main(int argc, char **argv) {
    mutation = argc == 2 ? (unsigned)strtoul(argv[1], 0, 0) : 0;
    if (mutation > 6) return 98;
    int result = CASE_MAIN();
    if (calls != 1) return 99;
    return result;
}
