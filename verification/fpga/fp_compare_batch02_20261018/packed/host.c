#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "tables.h"
extern int ENTRY(void);
static unsigned calls, mutation;
static uint64_t fingerprint = UINT64_C(1469598103934665603);
static void hash(const void *p, unsigned n) {
    const unsigned char *s = p;
    while (n--) { fingerprint ^= *s++; fingerprint *= UINT64_C(1099511628211); }
}
unsigned long capacity(void) { return CAP; }
long replay_write(long n, long fd, long p, long len) {
    if (n != 64 || fd != 1 || len < 0) abort();
    return fwrite((void *)p, 1, len, stdout);
}
static unsigned long invoke(unsigned op, const void *a, const void *b, void *out,
                            unsigned long vl, unsigned long cap, const void *m,
                            unsigned long start, unsigned long sticky) {
    if (calls >= BOUND) abort();
    const struct packed_case *g = &records[calls];
    if (op != g->op || vl != g->vl || cap != CAP || start || sticky != g->sticky ||
        memcmp(a, input_rows[g->ai], CAP * 4) || memcmp(b, input_rows[g->bi], CAP * 4)) abort();
    const uint8_t *mask = m;
    uint8_t *v = out;
    for (unsigned i = 0; i < 128; ++i)
        if (mask[i] != (uint8_t)mask_rows[g->mode]) abort();
    for (unsigned i = 0; i < 130; ++i) if (v[(int)i - 1] != 0x5b) abort();
    hash(a, CAP * 4); hash(b, CAP * 4); hash(m, 128);
    uint64_t args[] = {op, vl, cap, start, sticky}; hash(args, sizeof(args));
    for (unsigned i = 0; i < CAP / 8; ++i) {
        unsigned flexible = ~(g->must_zero[i] | g->must_one[i]) & 255;
        v[i] = g->must_one[i] | (flexible & (mutation == 1 ? 255 : mutation == 2 ? 0xaa : 0));
    }
    unsigned long status = (unsigned long)g->flags << 32;
    if (++calls == BOUND) {
        if (mutation == 3 || mutation == 8) {
            unsigned flips = mutation == 8 ? 3 : 1;
            for (unsigned i = 0; i < CAP && flips; ++i)
                if (((g->must_zero[i / 8] | g->must_one[i / 8]) >> (i % 8)) & 1) {
                    v[i / 8] ^= 1U << (i % 8); --flips;
                }
        }
        if (mutation == 4 || mutation == 8) status ^= 1UL << 36;
        if (mutation == 5 || mutation == 9) v[-1] ^= 1;
        if (mutation == 6 || mutation == 9) v[CAP / 8] ^= 1;
        if (mutation == 7 || mutation == 8) status |= 3;
    }
    return status;
}
#define OP(N) unsigned long op_##N(const void *a,const void *b,void *o,unsigned long v, unsigned long c,const void *m,unsigned long s,unsigned long f) { return invoke(N,a,b,o,v,c,m,s,f); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
int main(int argc, char **argv) {
    if (argc != 2) return 99;
    mutation = strtoul(argv[1], 0, 0);
    int rc = ENTRY();
    if (calls != BOUND) abort();
    printf("HOST_FLOW calls=%u fingerprint=%016llx\n", calls, (unsigned long long)fingerprint);
    return rc;
}
