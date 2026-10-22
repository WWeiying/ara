#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr,"HOST_REJECT line=%d %s\n",__LINE__,#c); exit(90); } } while (0)
#if !ORIGINAL_RUN
static void host_store(void *, unsigned, uint64_t, unsigned);
static uint32_t host_lwu(const void *);
#include "case.c"
#include "original_oracle.h"
#else
#include "original_case.c"
#endif

static unsigned call_number, event_count, lwu_count, mode_kind;
static const char *negative_mode;
static char transcript[32768];
static unsigned transcript_length;
static unsigned long equivalence_checks;
#if !ORIGINAL_RUN
static struct { void *base; unsigned offset, width; } events[49];

static int negative(const char *name) {
    return negative_mode && !strcmp(negative_mode, name);
}

static void host_store(void *base, unsigned offset, uint64_t value, unsigned width) {
    CHECK(event_count < 49);
    CHECK((base == a || base == b) ? width == 8 && offset < 64 && offset % 8 == 0 :
          base == mask ? width == 8 && offset < 128 && offset % 8 == 0 :
          base == output && ((width == 8 && offset < 128 && offset % 8 == 0) ||
                             (width == 2 && offset == 128)));
    /* Call two has identical setup: detecting omitted stores must not depend on value changes. */
    if (call_number == 1 && ((negative("missing_same_input") && base == a && offset == 56) ||
        (negative("missing_same_mask") && base == mask && offset == 120) ||
        (negative("missing_same_tail") && base == output && offset == 128))) return;
    events[event_count].base = base;
    events[event_count].offset = offset;
    events[event_count++].width = width;
    if (negative("wrong_high_input") && base == a && offset == 56) value ^= UINT64_C(1) << 63;
    memcpy((uint8_t *)base + offset, &value, width);
}

static uint32_t host_lwu(const void *address) {
    uint32_t value;
    CHECK(address == output && !((uintptr_t)address & 3));
    memcpy(&value, address, 4);
    ++lwu_count;
    return value;
}

static void compare_oracle(unsigned op, unsigned seed, unsigned vl, unsigned mode,
                           unsigned sticky, uint32_t observed, uint64_t status,
                           uint64_t record, unsigned expected_flags) {
    uint32_t prior;
    memcpy(&prior, output, 4);
    memcpy(output, &observed, 4);
    unsigned exact_flags = 0;
    unsigned original = original_oracle(op, seed, vl, mode, sticky, status, &exact_flags);
    CHECK(exact_flags == expected_flags);
    CHECK(packed_errors(observed, status, record, expected_flags) == original);
    memcpy(output, &prior, 4);
    ++equivalence_checks;
}
#endif

long replay_write(long n, long fd, long pointer, long length) {
    CHECK(n == 64 && fd == 1 && length >= 0);
    CHECK(transcript_length + (unsigned long)length < sizeof(transcript));
    memcpy(transcript + transcript_length, (const void *)pointer, length);
    transcript_length += length;
    transcript[transcript_length] = 0;
    return length;
}

unsigned long capacity(void) { return 16; }

static unsigned long operate(unsigned op, const void *pa, const void *pb, void *pd,
                             unsigned long vl, unsigned long cap, const void *pm,
                             unsigned long start, unsigned long sticky) {
    const unsigned lengths[] = {0, 1, 2, 3, 8, 15, 16};
    unsigned n = call_number, want_sticky = n % 2; n /= 2;
    unsigned mode = n % 4; n /= 4;
    unsigned li = n % 7; n /= 7;
    unsigned want_op = n % 10, seed = n / 10;
    CHECK(seed < 32 && op == want_op && vl == lengths[li] && cap == 16);
    CHECK(start == 0 && sticky == want_sticky);
    CHECK(pa == a && pb == b && pm == mask && pd == output + 1);
    CHECK(sizeof(word) == 4 && sizeof(a) == 4096 && sizeof(b) == 4096);
#if !ORIGINAL_RUN
    CHECK(event_count == 49);
    for (unsigned i = 0; i < 16; ++i) {
        CHECK(events[i].base == mask && events[i].offset == i*8 && events[i].width == 8);
        CHECK(events[32+i].base == output && events[32+i].offset == i*8 && events[32+i].width == 8);
    }
    for (unsigned i = 0; i < 8; ++i) {
        CHECK(events[16+2*i].base == a && events[16+2*i].offset == i*8 && events[16+2*i].width == 8);
        CHECK(events[17+2*i].base == b && events[17+2*i].offset == i*8 && events[17+2*i].width == 8);
    }
    CHECK(events[48].base == output && events[48].offset == 128 && events[48].width == 2);
    event_count = 0;
    if (negative("wrong_raw_seed") && seed == 1 && op == 4) b[0] = 0;
#endif
    for (unsigned i = 0; i < 16; ++i) {
        CHECK(a[i] == inputs[lhs_index(seed, i)]);
        CHECK(b[i] == inputs[rhs_index(seed, i, op)]);
    }
    for (unsigned i = 16; i < 1024; ++i) CHECK(a[i] == 0 && b[i] == 0);
    const uint8_t masks[] = {255, 170, 36, 0};
    for (unsigned i = 0; i < 128; ++i) CHECK(mask[i] == masks[mode]);
    for (unsigned i = 0; i < 130; ++i) CHECK(output[i] == 91);
    uint16_t bits = 0;
    unsigned flags = (unsigned)sticky;
    for (unsigned i = 0; i < 16; ++i) {
        unsigned ai = lhs_index(seed, i), bi = op < 4 ? rhs_index(seed, i, op) : 14;
        struct fixture wanted = expected[op < 4 ? op : op - 4][ai][bi];
        bits |= (i < vl ? wanted.bit : ((91U >> (i % 8)) & 1U)) << i;
        if (i < vl) flags |= wanted.flags;
    }
    uint64_t status = (uint64_t)flags << 32;
#if !ORIGINAL_RUN
    uint32_t observed = 91U | ((uint32_t)bits << 8) | (91U << 24);
    uint64_t record = oracle_records[(seed*10+op)*7+li];
    CHECK(packed_errors(observed, status, record, flags) == 0);
    for (unsigned i = 0; i < 16; ++i)
        compare_oracle(op, seed, (unsigned)vl, mode, (unsigned)sticky,
                       observed ^ (1U << (i+8)), status, record, flags);
    const uint32_t changes[] = {0x300, 1, 0x1000000, 0x1000001};
    for (unsigned i = 0; i < 4; ++i)
        compare_oracle(op, seed, (unsigned)vl, mode, (unsigned)sticky,
                       observed ^ changes[i], status, record, flags);
    const uint64_t status_changes[] = {1, UINT64_C(1)<<32, UINT64_C(16)<<32, UINT64_C(1)<<63};
    for (unsigned i = 0; i < 4; ++i)
        compare_oracle(op, seed, (unsigned)vl, mode, (unsigned)sticky,
                       observed, status ^ status_changes[i], record, flags);
#endif
    if (mode_kind == 1 && call_number < 21) bits ^= 1;
    if (mode_kind == 2) {
        bits ^= 3;
        status ^= UINT64_C(17) << 32;
        status |= 1;
        output[0] ^= 1;
        output[3] ^= 1;
    }
    memcpy(output+1, &bits, 2);
    ++call_number;
    return status;
}

#define OP(N) unsigned long op_##N(const void *a,const void *b,void *c,unsigned long d, \
    unsigned long e,const void *f,unsigned long g,unsigned long h) { return operate(N,a,b,c,d,e,f,g,h); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)

int main(int argc, char **argv) {
    uint32_t endian = 1;
    CHECK(*(uint8_t *)&endian == 1 && argc == 2);
    if (!strcmp(argv[1], "details")) mode_kind = 1;
    else if (!strcmp(argv[1], "all_errors")) mode_kind = 2;
    else if (strcmp(argv[1], "positive")) negative_mode = argv[1];
    int rc = fp_compare_unboxed_e32_mf2_full17920_main();
    CHECK(call_number == 17920 && event_count == 0);
#if !ORIGINAL_RUN
    CHECK(lwu_count == 17920 && equivalence_checks == 430080);
#else
    CHECK(lwu_count == 0 && equivalence_checks == 0);
#endif
    CHECK(!negative_mode);
    unsigned details = 0;
    for (char *s = transcript; (s = strstr(s, "RVV_FP_COMPARE_DETAIL ")); ++s) ++details;
    if (mode_kind) CHECK(rc == 1 && details == 20);
    else CHECK(rc == 0 && details == 0 && !strcmp(transcript, "RVV_FP_COMPARE_PASS sew=32 cases=17920 errors=0\n"));
    if (mode_kind == 1) CHECK(strstr(transcript, "RVV_FP_COMPARE_FAIL sew=32 cases=17920 errors=21\n"));
    fputs(transcript, stdout);
    fprintf(stderr,"HOST_PASS original=%d mode=%s calls=%u lwu=%u comparisons=%lu details=%u\n",
            ORIGINAL_RUN, argv[1], call_number, lwu_count, equivalence_checks, details);
    return 0;
}
