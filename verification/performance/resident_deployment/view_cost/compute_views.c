#include "kernel_compute.h"
#include <stddef.h>
#include <stdint.h>

enum { D = 128, H = 2, T = 65, STRIDE = 2 * D, NAN16 = 0x7e00 };
extern const uint16_t capture_query[], capture_key[], capture_value[], capture_mask[];
extern const uint16_t updated_key[], updated_value[];
extern const uint32_t expected_output[3][H * D], expected_flags[3];

static struct {
    uint16_t before[32], data[T * STRIDE], after[32];
} key_view __attribute__((aligned(64))), value_view __attribute__((aligned(64)));
static struct {
    unsigned char before[64], data[32768], after[64];
} scratch __attribute__((aligned(64)));
static struct {
    unsigned char before[64];
    uint32_t data[H * D];
    unsigned char after[64];
} output __attribute__((aligned(64)));

void *memcpy(void *destination, const void *source, size_t bytes)
{
    unsigned char *out = destination;
    const unsigned char *in = source;
    for (size_t i = 0; i < bytes; ++i) out[i] = in[i];
    return destination;
}

void *memset(void *destination, int value, size_t bytes)
{
    unsigned char *out = destination;
    for (size_t i = 0; i < bytes; ++i) out[i] = (unsigned char)value;
    return destination;
}

static void put(char c) { *(volatile unsigned char *)0xc0000000UL = (unsigned char)c; }
static void text(const char *s) { while (*s) put(*s++); }
static void hex(uint32_t value)
{
    const char digits[] = "0123456789abcdef";
    for (int shift = 28; shift >= 0; shift -= 4) put(digits[(value >> shift) & 15]);
}
static void hex64(uintptr_t value) { hex((uint32_t)(value >> 32)); hex((uint32_t)value); }
static void *kernel_alias(const void *pointer)
{
    return (void *)((uintptr_t)pointer - 0x80000000UL + 0xffffffc000000000UL);
}

void trap_report(uintptr_t cause, uintptr_t address, uintptr_t pc)
{
    text("RESIDENT_VIEWS_TRAP cause="); hex64(cause);
    text(" badaddr="); hex64(address); text(" pc="); hex64(pc); put('\n');
}

static void fill_views(void)
{
    for (unsigned i = 0; i < 32; ++i) {
        key_view.before[i] = key_view.after[i] = NAN16;
        value_view.before[i] = value_view.after[i] = NAN16;
    }
    for (unsigned i = 0; i < T * STRIDE; ++i)
        key_view.data[i] = value_view.data[i] = NAN16;
}

/* Select head one; head zero is NaN padding, including the leading gap. */
static unsigned store_rows(const uint16_t *key, const uint16_t *value, int update)
{
    unsigned changed = 0;
    for (unsigned t = 0; t < T; ++t)
        for (unsigned d = 0; d < D; ++d) {
            unsigned src = t * D + d, dst = t * STRIDE + D + d;
            if (update) {
                changed += key_view.data[dst] != key[src];
                changed += value_view.data[dst] != value[src];
            }
            key_view.data[dst] = key[src];
            value_view.data[dst] = value[src];
        }
    asm volatile("fence rw,rw" ::: "memory");
    return changed;
}

static unsigned check_views(const uint16_t *key, const uint16_t *value)
{
    unsigned errors = 0;
    for (unsigned i = 0; i < 32; ++i) {
        errors += key_view.before[i] != NAN16 || key_view.after[i] != NAN16;
        errors += value_view.before[i] != NAN16 || value_view.after[i] != NAN16;
    }
    for (unsigned t = 0; t < T; ++t)
        for (unsigned d = 0; d < D; ++d) {
            unsigned src = t * D + d, gap = t * STRIDE + d, live = gap + D;
            errors += key_view.data[gap] != NAN16 || value_view.data[gap] != NAN16;
            errors += key_view.data[live] != key[src] || value_view.data[live] != value[src];
        }
    return errors;
}

static void addresses(unsigned trial, const struct ara_resident_compute_buffers *b)
{
    text("RESIDENT_VIEWS_ADDRESS case="); hex(trial);
    text(" query="); hex64((uintptr_t)b->query);
    text(" key="); hex64((uintptr_t)b->key);
    text(" value="); hex64((uintptr_t)b->value);
    text(" mask="); hex64((uintptr_t)b->mask);
    text(" output="); hex64((uintptr_t)b->output);
    text(" scratch="); hex64((uintptr_t)b->scratch);
    text(" kstride="); hex(b->key_token_stride);
    text(" vstride="); hex(b->value_token_stride); put('\n');
}

int main(void)
{
    if (ara_resident_compute_scratch_bytes() > sizeof(scratch.data)) {
        text("RESIDENT_VIEWS_FAIL scratch_size\n");
        return 1;
    }
    fill_views();
    store_rows(capture_key, capture_value, 0);
    for (unsigned trial = 0; trial < 3; ++trial) {
        unsigned changed = trial == 2 ? store_rows(updated_key, updated_value, 1) : 0;
        const uint16_t *key = trial == 2 ? updated_key : capture_key;
        const uint16_t *value = trial == 2 ? updated_value : capture_value;
        struct ara_resident_compute_buffers b = {
            .query = kernel_alias(capture_query),
            .key = kernel_alias(trial ? key_view.data + D : capture_key),
            .value = kernel_alias(trial ? value_view.data + D : capture_value),
            .mask = kernel_alias(capture_mask), .output = kernel_alias(output.data),
            .scratch = kernel_alias(scratch.data), .scratch_bytes = sizeof(scratch.data),
            .heads = H, .dimension = D, .tokens = T, .scale_bits = 0x3db504f3,
            .flags = ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS,
            .key_token_stride = trial ? STRIDE * 2 : 0,
            .value_token_stride = trial ? STRIDE * 2 : 0,
        };
        memset(&output, 0xa5, sizeof(output));
        memset(scratch.before, 0xa5, sizeof(scratch.before));
        memset(scratch.after, 0xa5, sizeof(scratch.after));
        addresses(trial, &b);
        int status = ara_resident_compute(&b);
        unsigned fcsr;
        asm volatile("csrr zero,vl\nfence rw,rw\ncsrr %0,fcsr" : "=r"(fcsr) : : "memory");
        unsigned errors = check_views(key, value);
        for (unsigned i = 0; i < H * D; ++i) errors += output.data[i] != expected_output[trial][i];
        for (unsigned i = 0; i < 64; ++i) {
            errors += output.before[i] != 0xa5 || output.after[i] != 0xa5;
            errors += scratch.before[i] != 0xa5 || scratch.after[i] != 0xa5;
        }
        errors += status != 0 || b.started != 1 || b.resident_used != 1;
        errors += b.flags != expected_flags[trial] || fcsr != expected_flags[trial];
        errors += trial == 2 && changed == 0;
        text("RESIDENT_VIEWS_RESULT case="); hex(trial);
        text(" status="); hex((uint32_t)status); text(" flags="); hex(b.flags);
        text(" fcsr="); hex(fcsr); text(" started="); hex(b.started);
        text(" used="); hex(b.resident_used); text(" changed="); hex(changed);
        text(" errors="); hex(errors); put('\n');
        for (unsigned i = 0; i < H * D; ++i) {
            text("RESIDENT_VIEWS_OUTPUT case="); hex(trial);
            text(" index="); hex(i); text(" bits="); hex(output.data[i]); put('\n');
        }
        if (errors) {
            text("RESIDENT_VIEWS_FAIL\n");
            return 1;
        }
    }
    text("RESIDENT_VIEWS_PASS\n");
    return 0;
}
