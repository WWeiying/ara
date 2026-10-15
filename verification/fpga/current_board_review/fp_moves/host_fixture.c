#include <stdint.h>
#include <stdio.h>

extern int CASE_MAIN(void);
long replay_write(long number, long fd, long pointer, long length) {
    if (number != 64 || fd != 1 || length < 0) return -1;
    return fwrite((const void *)pointer, 1, length, stdout);
}
unsigned long capacity(void) { return 64; }

/* Host-only oracle sanity: never counts as executing vector RTL. */
#define ARGS const void *a, const void *s, void *d, unsigned long vl, \
    unsigned long cap, const void *m, unsigned long control, void *result
unsigned long op_6(ARGS) {
    (void)a; (void)m; (void)result;
    uint16_t *out = d;
    unsigned long start = (uint32_t)control;
    if (start < vl && HOST_MUTATION != 1) out[0] = *(const uint64_t *)s;
    if (HOST_MUTATION == 2) out[cap - 1] ^= 1;
    return control & UINT64_C(0xffffffff00000000);
}
#define UNUSED_OP(n) unsigned long op_##n(ARGS) { \
    (void)a; (void)s; (void)d; (void)vl; (void)cap; (void)m; \
    (void)control; (void)result; return 1; }
UNUSED_OP(0)
UNUSED_OP(1)
UNUSED_OP(2)
UNUSED_OP(3)
UNUSED_OP(4)
UNUSED_OP(5)
UNUSED_OP(7)
int main(void) { return CASE_MAIN(); }
