/* Same-source derivative: direct trials, original setup and bytewise oracle. */
#include <stdint.h>

static uint8_t input[1024], output[1026], expected[1024], mask[128];
typedef unsigned long (*operation)(const void *, void *, const void *,
                                  unsigned long, unsigned long, unsigned long);
#define DECLARE(name) extern unsigned long name(const void *, void *, const void *, \
    unsigned long, unsigned long, unsigned long)
DECLARE(op_0); DECLARE(op_1); DECLARE(op_2); DECLARE(op_3);
DECLARE(op_0_masked); DECLARE(op_1_masked); DECLARE(op_2_masked); DECLARE(op_3_masked);
DECLARE(op_0_unmasked); DECLARE(op_1_unmasked); DECLARE(op_2_unmasked); DECLARE(op_3_unmasked);
extern unsigned long capacity(void);
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long, unsigned long, unsigned long, unsigned long);
static operation functions[] = {op_0, op_1, op_2, op_3,
    op_0_masked, op_1_masked, op_2_masked, op_3_masked,
    op_0_unmasked, op_1_unmasked, op_2_unmasked, op_3_unmasked};
struct trial { unsigned op, mode, start, vl, unmasked, seed; };
#include "test_cases.h"

static void number(unsigned value) {
    char s[16]; unsigned i = 15; s[i] = 0;
    do { s[--i] = '0' + value % 10; value /= 10; } while (value);
    replay_text(s + i);
}

static uint64_t load_word(const uint8_t *p, unsigned bytes) {
    uint64_t x = 0;
    for (unsigned b = 0; b < bytes; ++b) x |= (uint64_t)p[b] << (8 * b);
    return x;
}

static void store_word(uint8_t *p, unsigned bytes, uint64_t x) {
    for (unsigned b = 0; b < bytes; ++b) p[b] = x >> (8 * b);
}

int matrix_main(void) {
    unsigned cap = capacity(), errors = 0;
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
    unsigned bytes = DEST_REGS * vlenb, source_bytes = SEW / FACTOR / 8;
    if (vlenb != 128 || cap != EXPECTED_CAP || bytes > 1024 || cap * source_bytes > 1024)
        return 2;
    for (unsigned t = 0; t < sizeof(trials) / sizeof(trials[0]); ++t) {
        const struct trial *c = &trials[t];
        for (unsigned i = 0; i < cap * source_bytes; ++i)
            input[i] = (i * 73 + c->seed * 19) ^ 0x85;
        for (unsigned i = 0; i < 128; ++i)
            mask[i] = c->mode == 0 ? 255 : c->mode == 1 ? 0 : c->mode == 2 ? 0xaa : 0x24;
        for (unsigned i = 0; i < 1026; ++i) output[i] = 0x5b;
        for (unsigned i = 0; i < bytes; ++i) expected[i] = 0x5b;
        if (c->op >= 2) {
            unsigned offset = (DEST_REGS - SOURCE_REGS) * vlenb;
            for (unsigned i = 0; i < cap * source_bytes; ++i) expected[offset + i] = input[i];
        }
        for (unsigned i = c->start; i < c->vl; ++i) {
            if (!c->unmasked && !((mask[i / 8] >> (i % 8)) & 1)) continue;
            uint64_t x = load_word(input + i * source_bytes, source_bytes);
            if (c->op % 2) {
                uint64_t sign = UINT64_C(1) << (SEW / FACTOR - 1);
                x = (uint64_t)(int64_t)((x ^ sign) - sign);
            }
            store_word(expected + i * (SEW / 8), SEW / 8, x);
        }
        replay_text("EXTENSION_TRIAL "); number(t); replay_text("\n");
        unsigned index = c->op + (c->unmasked ? 8 : c->start ? 4 : 0);
        unsigned long restart = functions[index](input, output + 1, mask,
                                                 c->vl, cap, c->start);
        if (restart) errors += replay_mismatch(t, bytes + 2, 0, restart);
        for (unsigned i = 0; i < bytes; ++i) {
            if (output[i + 1] != expected[i]) {
                if (errors < 8) replay_mismatch(t, i, expected[i], output[i + 1]);
                ++errors;
            }
        }
        if (output[0] != 0x5b || output[bytes + 1] != 0x5b) ++errors;
        if (errors) break;
    }
    replay_text(errors ? "EXTENSION_MATRIX_FAIL sew=" : "EXTENSION_MATRIX_PASS sew=");
    number(SEW); replay_text(" factor="); number(FACTOR);
    replay_text(" cases="); number(sizeof(trials) / sizeof(trials[0]));
    replay_text(" errors="); number(errors); replay_text("\n");
    return errors != 0;
}
