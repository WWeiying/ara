#include <stdio.h>
#include <stdlib.h>

static FILE *capture;
static unsigned calls, injected;
unsigned long capacity(void) { return 512; }
long replay_write(long n, long fd, long p, long z) {
    if (n != 64 || fd != 1 || z < 0) abort();
    return fwrite((void *)p, 1, z, stdout);
}

static unsigned long emulate(unsigned op, const void *aa, const void *ss,
        void *oo, unsigned long vl, unsigned long cap, const void *mm,
        unsigned long control, void *result) {
    const uint16_t *a = aa;
    const uint8_t *m = mm;
    uint16_t *o = oo;
    uint64_t scalar = *(const uint64_t *)ss;
    unsigned start = (uint32_t)control, flags = control >> 32;
    if (op != 0 || cap != 512) abort();
    if (calls < 195 && capture) {
        uint64_t header[] = {op, vl, cap, control, scalar, *(uint64_t *)result};
        if (fwrite(header, sizeof(header), 1, capture) != 1 ||
            fwrite(a, cap * sizeof(*a), 1, capture) != 1 ||
            fwrite(o - 1, (cap + 2) * sizeof(*o), 1, capture) != 1 ||
            fwrite(m, 128, 1, capture) != 1) abort();
    }
    /* Bit-move model: no host floating-point arithmetic or shared oracle helper. */
    uint16_t value = (scalar >> 16) == UINT64_C(0xffffffffffff) ?
                     (uint16_t)scalar : UINT16_C(0x7e00);
    for (unsigned i = start; i < vl; ++i)
        o[i] = ((m[i / 8] >> (i % 8)) & 1) ? value : a[i];
    unsigned returned_start = 0;
    if (!injected) {
        if (HOST_MUTATION == 1 && start < vl) { o[start] ^= 1; injected = 1; }
        if (HOST_MUTATION == 2 && start) { o[0] ^= 1; injected = 1; }
        if (HOST_MUTATION == 3 && start < vl && vl < cap) { o[vl] ^= 1; injected = 1; }
        if (HOST_MUTATION == 4) {
            for (unsigned i = start; i < vl; ++i)
                if (!((m[i / 8] >> (i % 8)) & 1)) {
                    o[i] ^= 1; injected = 1; break;
                }
        }
        if (HOST_MUTATION == 5) { o[-1] ^= 1; injected = 1; }
        if (HOST_MUTATION == 6) { o[cap] ^= 1; injected = 1; }
        if (HOST_MUTATION == 7) { returned_start = 1; injected = 1; }
        if (HOST_MUTATION == 8) { flags ^= 16; injected = 1; }
        if (HOST_MUTATION == 9) { *(uint64_t *)result ^= 1; injected = 1; }
    }
    ++calls;
    return ((uint64_t)flags << 32) | returned_start;
}

#define OP(N) unsigned long op_##N(const void *a, const void *s, void *o, \
    unsigned long vl, unsigned long cap, const void *m, unsigned long c, void *r) { \
    return emulate(N, a, s, o, vl, cap, m, c, r); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7)

int main(int argc, char **argv) {
    if (argc == 2) {
        capture = fopen(argv[1], "wbx");
        if (!capture) abort();
    } else if (argc != 1) abort();
    int status = fp_merge_prefix195_main();
    if (capture && fclose(capture)) abort();
    if (HOST_MUTATION && !injected) abort();
    if (calls != HOST_CALLS) abort();
    return status;
}
