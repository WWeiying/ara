#include <stdint.h>
#include "operations.h"
#include "tables.h"

typedef unsigned long (*operation)(const void *, const void *, void *, unsigned long,
                                   unsigned long, const void *, unsigned long, unsigned long);
static operation functions[] = {FUNCTIONS};
extern unsigned long capacity(void);
extern long replay_write(long, long, long, long);
static uint64_t a[CAP / 2], b[CAP / 2], mask[16], output_words[17];
static uint8_t *const output = (uint8_t *)output_words;

static void text(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    replay_write(64, 1, (long)s, n);
}
static void num(unsigned n) {
    char s[16]; unsigned i = sizeof(s) - 1; s[i] = 0;
    do { s[--i] = '0' + n % 10; n /= 10; } while (n);
    text(s + i);
}

int packed_main(void) {
    if (capacity() != CAP) { text("RVV_FP_COMPARE_CAPACITY_FAIL\n"); return 2; }
    unsigned errors = 0, details = 0;
    for (unsigned c = 0; c < BOUND; ++c) {
        const struct packed_case *g = &records[c];
        unsigned prior = errors;
        for (unsigned i = 0; i < CAP / 2; ++i) {
            a[i] = input_rows[g->ai][i];
            b[i] = input_rows[g->bi][i];
        }
        for (unsigned i = 0; i < 16; ++i) {
            mask[i] = mask_rows[g->mode];
            output_words[i] = UINT64_C(0x5b5b5b5b5b5b5b5b);
        }
        output[128] = output[129] = 0x5b;
        unsigned long status = functions[g->op](a, b, output + 1, g->vl, CAP,
                                                mask, 0, g->sticky);
        errors += (uint32_t)status != 0;
        for (unsigned i = 0; i < CAP / 8; ++i) {
            uint8_t v = output[i + 1];
            uint8_t bad = (v & g->must_zero[i]) | ((uint8_t)~v & g->must_one[i]);
            errors += popcounts[bad];
        }
        errors += (status >> 32) != g->flags;
        errors += output[0] != 0x5b || output[CAP / 8 + 1] != 0x5b;
        if (errors != prior && details++ < 20) {
            text("RVV_FP_COMPARE_DETAIL op="); num(g->op);
            text(" seed="); num(g->seed);
            text(" vl="); num(g->vl);
            text(" mask="); num(g->mode);
            text(" sticky="); num(g->sticky);
            text(" expected_flags="); num(g->flags);
            text(" actual_flags="); num(status >> 32);
            text(" errors="); num(errors - prior); text("\n");
        }
    }
    text(errors ? "RVV_FP_COMPARE_FAIL sew=32 cases=" : "RVV_FP_COMPARE_PASS sew=32 cases=");
    num(BOUND); text(" errors="); num(errors); text("\n");
    return errors ? 1 : 0;
}
