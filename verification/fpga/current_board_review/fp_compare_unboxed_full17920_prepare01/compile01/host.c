#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static void host_store(void *, unsigned, uint64_t, unsigned);
static uint32_t host_lwu(const void *);
#include "case.c"

static unsigned call_number, event_count, lwu_count, inject_errors;
static const char *negative_mode;
static char transcript[16384];
static unsigned transcript_length;
static struct { void *base; unsigned offset, width; } events[42];
static unsigned long equivalence_checks;

static void host_store(void *base, unsigned offset, uint64_t value, unsigned width) {
    assert(event_count < 41);
    if (negative_mode && !strcmp(negative_mode, "missing_input_store") && base == a && offset == 24)
        return;
    if (negative_mode && !strcmp(negative_mode, "missing_mask_store") && base == mask && offset == 120)
        return;
    if (negative_mode && !strcmp(negative_mode, "missing_output_tail") && base == output && offset == 128)
        return;
    events[event_count].base = base;
    events[event_count].offset = offset;
    events[event_count++].width = width;
    memcpy((unsigned char *)base + offset, &value, width);
}

static uint32_t host_lwu(const void *address) {
    uint32_t value;
    assert(address == output && !((uintptr_t)address & 3));
    memcpy(&value, address, sizeof(value));
    ++lwu_count;
    return value;
}

long replay_write(long n, long fd, long pointer, long length) {
    assert(n == 64 && fd == 1 && length >= 0);
    assert(transcript_length + (unsigned long)length < sizeof(transcript));
    memcpy(transcript + transcript_length, (const void *)pointer, length);
    transcript_length += length;
    transcript[transcript_length] = 0;
    return length;
}

unsigned long capacity(void) { return 16; }

static unsigned allowed_bit(unsigned op, unsigned seed, unsigned vl, unsigned i,
                            unsigned bitvalue, unsigned *flags) {
    unsigned ai = (i + seed + 7 * (seed / 16)) % 16;
    unsigned bi = op < 4 ? (i * 3 + seed * 5 + seed / 16) % 16 : 14;
    struct fixture w = expected[op < 4 ? op : op - 4][ai][bi];
    unsigned old = (0x5b >> (i % 8)) & 1;
    if (i < vl) { *flags |= w.flags; return bitvalue == w.bit; }
    if (vl == 0) return bitvalue == old;
    return bitvalue == old || bitvalue == 1 || bitvalue == w.bit;
}

static unsigned original_errors(unsigned op, unsigned seed, unsigned vl,
                                unsigned sticky, uint32_t value, uint64_t status) {
    unsigned errors = (uint32_t)status != 0, flags = sticky;
    for (unsigned i = 0; i < 16; ++i)
        errors += !allowed_bit(op, seed, vl, i, (value >> (i + 8)) & 1, &flags);
    errors += (status >> 32) != flags;
    errors += (value & 255) != 91 || (value >> 24) != 91;
    return errors;
}

static unsigned long operate(unsigned op, const void *pa, const void *pb, void *pd,
                             unsigned long vl, unsigned long cap, const void *pm,
                             unsigned long start, unsigned long sticky) {
    const unsigned lengths[7] = {0, 1, 2, 3, 8, 15, 16};
    unsigned n = call_number, want_sticky = n % 2; n /= 2;
    unsigned mode = n % 4; n /= 4;
    unsigned li = n % 7; n /= 7;
    unsigned want_op = n % 10, seed = n / 10;
    assert(seed < 32 && op == want_op && vl == lengths[li] && cap == 16);
    assert(start == 0 && sticky == want_sticky);
    assert(pa == a && pb == b && pm == mask && pd == output + 1);
    assert(event_count == 41);
    for (unsigned i = 0; i < 16; ++i) {
        assert(events[i].base == mask && events[i].offset == i * 8 && events[i].width == 8);
        assert(events[24+i].base == output && events[24+i].offset == i * 8 && events[24+i].width == 8);
    }
    for (unsigned i = 0; i < 4; ++i) {
        assert(events[16+2*i].base == a && events[16+2*i].offset == i*8 && events[16+2*i].width == 8);
        assert(events[17+2*i].base == b && events[17+2*i].offset == i*8 && events[17+2*i].width == 8);
    }
    assert(events[40].base == output && events[40].offset == 128 && events[40].width == 2);
    event_count = 0;
    if (negative_mode && !strcmp(negative_mode, "wrong_raw_seed") && seed == 1 && op == 4) b[0] = 0;
    for (unsigned i = 0; i < 16; ++i) {
        assert(a[i] == inputs[(i+seed+7*(seed/16))%16]);
        assert(b[i] == inputs[op < 4 ? (i*3+seed*5+seed/16)%16 : seed%16]);
    }
    for (unsigned i = 16; i < 1024; ++i) assert(a[i] == 0 && b[i] == 0);
    const unsigned char masks[4] = {255, 170, 36, 0};
    for (unsigned i = 0; i < 128; ++i) assert(mask[i] == masks[mode]);
    for (unsigned i = 0; i < 130; ++i) assert(output[i] == 91);
    uint16_t value = 0;
    unsigned flags = sticky;
    for (unsigned i = 0; i < 16; ++i) {
        unsigned ai = (i+seed+7*(seed/16))%16;
        unsigned bi = op < 4 ? (i*3+seed*5+seed/16)%16 : 14;
        struct fixture w = expected[op < 4 ? op : op-4][ai][bi];
        value |= (i < vl ? w.bit : (91 >> (i%8)) & 1) << i;
        if (i < vl) flags |= w.flags;
    }
    uint32_t observed = 91U | ((uint32_t)value << 8) | (91U << 24);
    uint64_t status = (uint64_t)flags << 32;
    uint64_t record = oracle_records[(seed*10+op)*7+li];
    assert(packed_errors(observed, status, record, flags) == 0);
    for (unsigned i = 0; i < 16; ++i) {
        uint32_t changed = observed ^ (1U << (i+8));
        assert(packed_errors(changed, status, record, flags) ==
               original_errors(op, seed, vl, sticky, changed, status));
        ++equivalence_checks;
    }
    const uint32_t changes[] = {0x300, 1, 0x1000000, 0x1000001};
    for (unsigned i = 0; i < 4; ++i) {
        uint32_t changed = observed ^ changes[i];
        assert(packed_errors(changed, status, record, flags) ==
               original_errors(op, seed, vl, sticky, changed, status));
        ++equivalence_checks;
    }
    const uint64_t status_changes[] = {1, UINT64_C(1)<<32, UINT64_C(16)<<32};
    for (unsigned i = 0; i < 3; ++i) {
        assert(packed_errors(observed, status ^ status_changes[i], record, flags) ==
               original_errors(op, seed, vl, sticky, observed, status ^ status_changes[i]));
        ++equivalence_checks;
    }
    if (inject_errors && call_number < 21) value ^= 1;
    memcpy(output+1, &value, 2);
    ++call_number;
    return status;
}

#define OP(N) unsigned long op_##N(const void *a,const void *b,void *c,unsigned long d, \
    unsigned long e,const void *f,unsigned long g,unsigned long h) { return operate(N,a,b,c,d,e,f,g,h); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)

int main(int argc, char **argv) {
    uint32_t endian = 1; assert(*(unsigned char *)&endian == 1);
    assert(argc == 2);
    if (!strcmp(argv[1], "details")) inject_errors = 1;
    else if (strcmp(argv[1], "positive")) negative_mode = argv[1];
    int rc = fp_compare_unboxed_e16_mf4_full17920_main();
    assert(call_number == 17920 && lwu_count == 17920 && event_count == 0);
    if (negative_mode) { fprintf(stderr, "NEGATIVE_NOT_REJECTED\n"); return 3; }
    unsigned details = 0;
    for (char *s = transcript; (s = strstr(s, "RVV_FP_COMPARE_DETAIL ")); ++s) ++details;
    if (inject_errors) {
        assert(rc == 1 && details == 20);
        assert(strstr(transcript, "RVV_FP_COMPARE_FAIL sew=16 cases=17920 errors=21\n"));
    } else {
        assert(rc == 0 && details == 0);
        assert(!strcmp(transcript, "RVV_FP_COMPARE_PASS sew=16 cases=17920 errors=0\n"));
    }
    printf("HOST_PASS mode=%s calls=%u lwu=%u comparisons=%lu details=%u\n",
           argv[1], call_number, lwu_count, equivalence_checks, details);
    return 0;
}
