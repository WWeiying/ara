/* SPDX-License-Identifier: Apache-2.0 */
/* Bounded HOST-only tests. Build as C11 or C++17 with -Isoftware/llama/platform/linux.
 * No ioctl, device access, payload allocation, or errno expectations. */
#include "view_layout.h"

#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifdef __cplusplus
#define STATIC_ASSERT(c, m) static_assert(c, m)
#else
#define STATIC_ASSERT(c, m) _Static_assert(c, m)
#endif

STATIC_ASSERT(sizeof(struct ara_resident_kv_view) == 96, "view ABI size");
STATIC_ASSERT(sizeof(struct ara_resident_view_release) == 32, "release ABI size");
STATIC_ASSERT(sizeof(struct ara_resident_batch) == 104, "batch ABI size");
STATIC_ASSERT(sizeof(struct ara_resident_batch_group) == 16, "group ABI size");
STATIC_ASSERT(sizeof(struct ara_resident_view_caps) == 64, "caps ABI size");
STATIC_ASSERT(offsetof(struct ara_resident_batch, fflags) == 28, "batch fflags");
STATIC_ASSERT(offsetof(struct ara_resident_batch, fflags) ==
              offsetof(struct ara_resident_job, fflags), "shared fflags offset");
STATIC_ASSERT(offsetof(struct ara_resident_batch, handle) == 32, "batch handle");
STATIC_ASSERT(offsetof(struct ara_resident_batch, groups) == 40, "batch groups");
STATIC_ASSERT(offsetof(struct ara_resident_batch, output) == 64, "batch output");
STATIC_ASSERT(offsetof(struct ara_resident_batch, completed) == 72, "batch completed");
STATIC_ASSERT(offsetof(struct ara_resident_batch, reserved) == 80, "batch reserved");
STATIC_ASSERT(offsetof(struct ara_resident_kv_view, key) == 40, "view key");
STATIC_ASSERT(offsetof(struct ara_resident_kv_view, handle) == 56, "view handle");
STATIC_ASSERT(offsetof(struct ara_resident_kv_view, reserved) == 64, "view reserved");
STATIC_ASSERT(offsetof(struct ara_resident_view_release, handle) == 8, "release handle");
STATIC_ASSERT(offsetof(struct ara_resident_view_release, reserved) == 16, "release reserved");
STATIC_ASSERT(_IOC_SIZE(ARA_RESIDENT_REGISTER_KV) == 96, "register ioctl size");
STATIC_ASSERT(_IOC_SIZE(ARA_RESIDENT_RELEASE_KV) == 32, "release ioctl size");
STATIC_ASSERT(_IOC_SIZE(ARA_RESIDENT_EXECUTE_BATCH) == 104, "batch ioctl size");
STATIC_ASSERT(_IOC_SIZE(ARA_RESIDENT_VIEW_CAPS) == 64, "caps ioctl size");
STATIC_ASSERT(ARA_RESIDENT_MAX_BATCH == 16, "group limit");
STATIC_ASSERT(ARA_RESIDENT_MAX_KV_HEADS == 32, "KV head limit");
STATIC_ASSERT(ARA_RESIDENT_MAX_HEADS == 8, "per-group query head limit");
STATIC_ASSERT(ARA_RESIDENT_MAX_TOKENS == 256, "token limit");
STATIC_ASSERT(ARA_RESIDENT_MAX_VIEW_BYTES == 1048576, "view byte limit");

typedef unsigned __int128 wide;
static uint64_t checks, failures, case_id, seed;
static const char *phase;
static const unsigned dimensions[] = {64, 96, 128};

static void check(int ok, const char *expression, unsigned line)
{
    ++checks;
    if (ok) return;
    if (failures++ < 32)
        fprintf(stderr, "FAIL %s seed=%" PRIu64 " case=%" PRIu64
                " line=%u: %s\n", phase, seed, case_id, line, expression);
}
#define CHECK(c) check(!!(c), #c, __LINE__)
#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

static uint64_t random64(uint64_t *state)
{
    /* SplitMix64: independent reproducible streams, including seed zero. */
    uint64_t z = (*state += UINT64_C(0x9e3779b97f4a7c15));
    z = (z ^ (z >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27)) * UINT64_C(0x94d049bb133111eb);
    return z ^ (z >> 31);
}

static int dimension_ok(unsigned d)
{
    return d == 64 || d == 96 || d == 128;
}

static int address_fits(uint64_t address, wide size)
{
    return (wide)address + size <= UINT64_MAX;
}

static int overlap_oracle(uint64_t a, uint64_t na, uint64_t b, uint64_t nb)
{
    wide end_a = (wide)a + na, end_b = (wide)b + nb;
    wide start = a > b ? a : b;
    wide end = end_a < end_b ? end_a : end_b;
    return na && nb && start < end;
}

/* Walk rows in each permitted physical order, rather than copying the helper's
 * span/stride inequality. Exotic non-major weaving is not an ABI requirement. */
static int extent_oracle(unsigned d, unsigned heads, unsigned tokens,
                         unsigned ts, unsigned hs, uint64_t *bytes)
{
    if (!heads || !tokens || ts % 64 || hs % 64 ||
        (wide)ts < (wide)d * 2 || (wide)hs < (wide)d * 2) return 0;
    for (unsigned order = 0; order != 2; ++order) {
        unsigned outer = order ? tokens : heads;
        unsigned inner = order ? heads : tokens;
        wide end = 0;
        int ordered = 1;
        for (unsigned i = 0; i < outer && ordered; ++i) {
            for (unsigned j = 0; j < inner; ++j) {
                wide start = (wide)i * (order ? ts : hs) +
                             (wide)j * (order ? hs : ts);
                if (start < end) { ordered = 0; break; }
                end = start + (wide)d * 2;
            }
        }
        if (ordered) {
            if (end > ARA_RESIDENT_MAX_VIEW_BYTES) return 0;
            *bytes = (uint64_t)end;
            return 1;
        }
    }
    return 0;
}

static int view_oracle(const struct ara_resident_kv_view *v, uint64_t *k, uint64_t *val)
{
    if (v->abi != 1 || v->bytes != 96 || !dimension_ok(v->dimension) ||
        !v->kv_heads || v->kv_heads > 32 || !v->capacity || v->capacity > 256 ||
        v->flags || v->handle || !v->key || !v->value || v->key % 64 || v->value % 64)
        return 0;
    for (unsigned i = 0; i < 4; ++i) if (v->reserved[i]) return 0;
    return extent_oracle(v->dimension, v->kv_heads, v->capacity,
                         v->key_token_stride, v->key_head_stride, k) &&
           extent_oracle(v->dimension, v->kv_heads, v->capacity,
                         v->value_token_stride, v->value_head_stride, val) &&
           address_fits(v->key, *k) && address_fits(v->value, *val);
}

/* Construct rows plus independent inter-row/inter-block padding. Counting those
 * bytes is a second extent oracle, independent of both the walk and the DUT. */
static uint64_t layout(unsigned d, unsigned h, unsigned t, unsigned token_major,
                       unsigned gap, unsigned block_gap, __u32 *ts, __u32 *hs)
{
    unsigned inner = token_major ? h : t;
    unsigned outer = token_major ? t : h;
    unsigned pitch = d * 2 + gap;
    *ts = token_major ? inner * pitch + block_gap : pitch;
    *hs = token_major ? pitch : inner * pitch + block_gap;
    return (uint64_t)h * t * d * 2 + ((uint64_t)h * t - 1) * gap +
           (uint64_t)(outer - 1) * block_gap;
}

static struct ara_resident_kv_view make_view(unsigned d, unsigned h, unsigned t,
        unsigned key_order, unsigned value_order, unsigned gap, unsigned block_gap,
        uint64_t *k, uint64_t *v)
{
    struct ara_resident_kv_view result;
    memset(&result, 0, sizeof(result));
    result.abi = 1;
    result.bytes = sizeof(result);
    result.dimension = d;
    result.kv_heads = h;
    result.capacity = t;
    result.key = UINT64_C(0x1000000);
    result.value = UINT64_C(0x2000000);
    *k = layout(d, h, t, key_order, gap, block_gap,
                &result.key_token_stride, &result.key_head_stride);
    *v = layout(d, h, t, value_order, block_gap, gap,
                &result.value_token_stride, &result.value_head_stride);
    return result;
}

static void expect_extent(unsigned d, unsigned h, unsigned t, unsigned ts, unsigned hs,
                          int expected, uint64_t bytes)
{
    __u32 actual = UINT32_C(0xdeadbeef);
    int accepted = ara_resident_view_extent(d, h, t, ts, hs, &actual);
    CHECK(!!accepted == !!expected);
    if (accepted) {
        CHECK(actual == bytes);
        CHECK(actual <= ARA_RESIDENT_MAX_VIEW_BYTES);
    }
}

static void expect_view(const struct ara_resident_kv_view *v, int expected,
                        uint64_t key, uint64_t value)
{
    struct ara_resident_view_sizes actual;
    struct ara_resident_kv_view before = *v;
    memset(&actual, 0xa5, sizeof(actual));
    int accepted = ara_resident_check_view(v, &actual);
    CHECK(!!accepted == !!expected);
    CHECK(memcmp(v, &before, sizeof(before)) == 0);
    if (accepted) {
        CHECK(actual.key == key);
        CHECK(actual.value == value);
        CHECK(actual.key <= ARA_RESIDENT_MAX_VIEW_BYTES);
        CHECK(actual.value <= ARA_RESIDENT_MAX_VIEW_BYTES);
    }
}

static void sweep_views(void)
{
    phase = "exhaustive views";
    for (unsigned di = 0; di < COUNT(dimensions); ++di)
        for (unsigned h = 1; h <= 32; ++h)
            for (unsigned t = 1; t <= 256; ++t)
                for (unsigned orders = 0; orders < 4; ++orders) {
                    uint64_t k, v;
                    ++case_id;
                    struct ara_resident_kv_view view = make_view(dimensions[di], h, t,
                            orders & 1, orders >> 1, 0, 0, &k, &v);
                    expect_extent(view.dimension, h, t, view.key_token_stride,
                                  view.key_head_stride, k <= ARA_RESIDENT_MAX_VIEW_BYTES, k);
                    expect_extent(view.dimension, h, t, view.value_token_stride,
                                  view.value_head_stride, v <= ARA_RESIDENT_MAX_VIEW_BYTES, v);
                    expect_view(&view, k <= ARA_RESIDENT_MAX_VIEW_BYTES &&
                                v <= ARA_RESIDENT_MAX_VIEW_BYTES, k, v);
                }
}

#define BAD_VIEW(field, val) do { \
    struct ara_resident_kv_view bad = base; \
    bad.field = (val); ++case_id; expect_view(&bad, 0, 0, 0); \
} while (0)

static void view_boundaries(void)
{
    phase = "view rejection and boundaries";
    uint64_t k, v;
    struct ara_resident_kv_view base = make_view(96, 3, 7, 0, 1, 64, 128, &k, &v);
    struct ara_resident_view_sizes sizes;
    CHECK(!ara_resident_check_view(NULL, &sizes));
    CHECK(!ara_resident_check_view(&base, NULL));
    expect_view(&base, 1, k, v);
    BAD_VIEW(abi, 0); BAD_VIEW(abi, 2); BAD_VIEW(abi, UINT32_MAX);
    BAD_VIEW(bytes, 0); BAD_VIEW(bytes, 95); BAD_VIEW(bytes, 97); BAD_VIEW(bytes, UINT32_MAX);
    BAD_VIEW(kv_heads, 0); BAD_VIEW(kv_heads, 33); BAD_VIEW(kv_heads, UINT32_MAX);
    BAD_VIEW(capacity, 0); BAD_VIEW(capacity, 257); BAD_VIEW(capacity, UINT32_MAX);
    BAD_VIEW(key, 0); BAD_VIEW(value, 0);
    for (unsigned d = 0; d <= 512; ++d)
        if (!dimension_ok(d)) { BAD_VIEW(dimension, d); }
    BAD_VIEW(dimension, UINT32_MAX);
    for (unsigned bit = 0; bit < 32; ++bit) { BAD_VIEW(flags, UINT32_C(1) << bit); }
    for (unsigned bit = 0; bit < 64; ++bit) {
        BAD_VIEW(handle, UINT64_C(1) << bit);
        for (unsigned i = 0; i < 4; ++i) { BAD_VIEW(reserved[i], UINT64_C(1) << bit); }
    }
    for (unsigned offset = 1; offset < 64; ++offset) {
        BAD_VIEW(key, base.key + offset); BAD_VIEW(value, base.value + offset);
        BAD_VIEW(key_token_stride, base.key_token_stride + offset);
        BAD_VIEW(key_head_stride, base.key_head_stride + offset);
        BAD_VIEW(value_token_stride, base.value_token_stride + offset);
        BAD_VIEW(value_head_stride, base.value_head_stride + offset);
    }
    const unsigned short_strides[] = {0, 64, 128};
    for (unsigned i = 0; i < COUNT(short_strides); ++i) {
        BAD_VIEW(key_token_stride, short_strides[i]);
        BAD_VIEW(key_head_stride, short_strides[i]);
        BAD_VIEW(value_token_stride, short_strides[i]);
        BAD_VIEW(value_head_stride, short_strides[i]);
    }
    BAD_VIEW(key_token_stride, UINT32_MAX & ~63u);
    BAD_VIEW(key_head_stride, UINT32_MAX & ~63u);
    BAD_VIEW(value_token_stride, UINT32_MAX & ~63u);
    BAD_VIEW(value_head_stride, UINT32_MAX & ~63u);
    /* Shrink a block stride by one cache line: the last/first rows now overlap. */
    base = make_view(96, 3, 7, 0, 1, 0, 0, &k, &v);
    BAD_VIEW(key_head_stride, base.key_head_stride - 64);
    BAD_VIEW(value_token_stride, base.value_token_stride - 64);
    BAD_VIEW(key_head_stride, base.key_token_stride);
    BAD_VIEW(value_token_stride, base.value_head_stride);

    for (unsigned di = 0; di < COUNT(dimensions); ++di) {
        unsigned d = dimensions[di], row = d * 2;
        /* Huge unused strides are legal, but must still meet ABI alignment/minimum. */
        for (unsigned axis = 0; axis < 2; ++axis) {
            base = make_view(d, axis ? 1 : 5, axis ? 5 : 1, 0, 0, 0, 0, &k, &v);
            if (axis) base.key_head_stride = base.value_head_stride = UINT32_MAX & ~63u;
            else base.key_token_stride = base.value_token_stride = UINT32_MAX & ~63u;
            expect_view(&base, 1, k, v);
            BAD_VIEW(key_token_stride, 0); BAD_VIEW(key_head_stride, 0);
            BAD_VIEW(value_token_stride, 0); BAD_VIEW(value_head_stride, 0);
            BAD_VIEW(key_token_stride, row - 64); BAD_VIEW(key_head_stride, row - 64);
            BAD_VIEW(value_token_stride, row - 64); BAD_VIEW(value_head_stride, row - 64);
            BAD_VIEW(key_token_stride, base.key_token_stride + 1);
            BAD_VIEW(key_head_stride, base.key_head_stride + 1);
            BAD_VIEW(value_token_stride, base.value_token_stride + 1);
            BAD_VIEW(value_head_stride, base.value_head_stride + 1);
        }
        base = make_view(d, 1, 1, 0, 0, 0, 0, &k, &v);
        base.key_token_stride = base.key_head_stride = UINT32_MAX & ~63u;
        base.value_token_stride = base.value_head_stride = UINT32_MAX & ~63u;
        expect_view(&base, 1, row, row);
        /* Last representable aligned end and the next aligned start that wraps. */
        base.key = base.value = (UINT64_MAX - row) & ~UINT64_C(63);
        expect_view(&base, 1, row, row);
        BAD_VIEW(key, base.key + 64); BAD_VIEW(value, base.value + 64);
        base = make_view(d, 1, 2, 0, 0, 0, 0, &k, &v);
        base.key_token_stride = base.value_token_stride = ARA_RESIDENT_MAX_VIEW_BYTES - row;
        expect_view(&base, 1, ARA_RESIDENT_MAX_VIEW_BYTES, ARA_RESIDENT_MAX_VIEW_BYTES);
        BAD_VIEW(key_token_stride, base.key_token_stride + 64);
        BAD_VIEW(value_token_stride, base.value_token_stride + 64);
        base = make_view(d, 2, 1, 1, 1, 0, 0, &k, &v);
        base.key_head_stride = base.value_head_stride = ARA_RESIDENT_MAX_VIEW_BYTES - row;
        expect_view(&base, 1, ARA_RESIDENT_MAX_VIEW_BYTES, ARA_RESIDENT_MAX_VIEW_BYTES);
        BAD_VIEW(key_head_stride, base.key_head_stride + 64);
        BAD_VIEW(value_head_stride, base.value_head_stride + 64);
    }
    /* K/V are read-only inputs: exact/partial address aliases are permitted here. */
    base = make_view(64, 2, 4, 0, 1, 0, 0, &k, &v);
    base.value = base.key;
    expect_view(&base, 1, k, v);
    base.value += 64;
    expect_view(&base, 1, k, v);
    /* Valid dimensions/counts but products exceeding 32 bits must not wrap small. */
    expect_extent(128, 32, 256, UINT32_C(0xffffffc0), UINT32_C(0xffffffc0), 0, 0);
    expect_extent(64, 1, 256, UINT32_C(0xffffffc0), 128, 0, 0);
    expect_extent(64, 32, 1, 128, UINT32_C(0xffffffc0), 0, 0);
}

static struct ara_resident_batch make_batch(unsigned d, unsigned tokens, unsigned count)
{
    struct ara_resident_batch b;
    memset(&b, 0, sizeof(b));
    b.abi = 1; b.bytes = sizeof(b); b.dimension = d; b.tokens = tokens; b.count = count;
    b.scale_bits = UINT32_C(0x3e000000);
    b.handle = 1; b.groups = 0x1000; b.query = 0x100000;
    b.mask = 0x200000; b.output = 0x300000;
    return b;
}

static int header_oracle(const struct ara_resident_batch *b)
{
    if (b->abi != 1 || b->bytes != 104 || b->count < 1 || b->count > 16 ||
        !b->handle || !dimension_ok(b->dimension) || b->tokens < 1 || b->tokens > 256 ||
        b->flags || b->fflags || b->completed || b->reserved0 || !b->groups ||
        !b->query || !b->mask || !b->output || b->groups % 8 || b->query % 2 ||
        b->mask % 2 || b->output % 4) return 0;
    for (unsigned i = 0; i < 3; ++i) if (b->reserved[i]) return 0;
    /* Decode IEEE-754 positive finite (0,1] without host floating point/FTZ. */
    unsigned sign = b->scale_bits >> 31;
    unsigned exponent = (b->scale_bits >> 23) & 255;
    unsigned mantissa = b->scale_bits & 0x7fffff;
    if (sign || (!exponent && !mantissa) || exponent > 127 ||
        (exponent == 127 && mantissa)) return 0;
    return address_fits(b->groups, (wide)b->count * 16);
}

static int batch_oracle(const struct ara_resident_batch *b,
        const struct ara_resident_batch_group *g, unsigned kv_heads,
        struct ara_resident_batch_sizes *s)
{
    if (!header_oracle(b) || !kv_heads || kv_heads > 32) return 0;
    memset(s, 0, sizeof(*s));
    for (unsigned i = 0; i < b->count; ++i) {
        if (!g[i].heads || g[i].heads > 8 || g[i].kv_head >= kv_heads || g[i].reserved)
            return 0;
        /* Sum each packed row's actual F16/F32 bytes, not a total-head formula. */
        for (unsigned head = 0; head < g[i].heads; ++head) {
            ++s->heads;
            for (unsigned d = 0; d < b->dimension; ++d) { s->query += 2; s->output += 4; }
        }
        s->groups += 16;
    }
    for (unsigned t = 0; t < b->tokens; ++t) s->mask += 2;
    return address_fits(b->query, s->query) && address_fits(b->mask, s->mask) &&
           address_fits(b->output, s->output);
}

static void expect_batch(const struct ara_resident_batch *b,
        const struct ara_resident_batch_group *g, unsigned kv_heads, int expected)
{
    struct ara_resident_batch_sizes want, actual;
    struct ara_resident_batch before = *b;
    struct ara_resident_batch_group groups_before[16];
    size_t group_bytes = b->count <= 16 ? b->count * sizeof(*g) : 0;
    memcpy(groups_before, g, group_bytes);
    CHECK(!!ara_resident_batch_header(b) == header_oracle(b));
    int reference = batch_oracle(b, g, kv_heads, &want);
    CHECK(reference == expected);
    memset(&actual, 0xa5, sizeof(actual));
    int accepted = ara_resident_check_batch(b, g, kv_heads, &actual);
    CHECK(!!accepted == expected);
    CHECK(memcmp(&before, b, sizeof(before)) == 0);
    CHECK(memcmp(groups_before, g, group_bytes) == 0);
    if (accepted && reference) {
        CHECK(actual.heads == want.heads); CHECK(actual.query == want.query);
        CHECK(actual.mask == want.mask); CHECK(actual.output == want.output);
        CHECK(actual.groups == want.groups);
        CHECK(actual.query <= ARA_RESIDENT_MAX_VIEW_BYTES);
        CHECK(actual.mask <= ARA_RESIDENT_MAX_VIEW_BYTES);
        CHECK(actual.output <= ARA_RESIDENT_MAX_VIEW_BYTES);
        CHECK(actual.groups <= ARA_RESIDENT_MAX_VIEW_BYTES);
    }
}

static void fill_groups(struct ara_resident_batch_group *g, unsigned count,
                         unsigned kv_heads, unsigned query_heads)
{
    memset(g, 0, count * sizeof(*g));
    for (unsigned i = 0; i < count; ++i) {
        g[i].kv_head = i % kv_heads;
        g[i].heads = query_heads ? query_heads : i % 8 + 1;
    }
}

static void sweep_batches(void)
{
    phase = "exhaustive batch shapes";
    struct ara_resident_batch_group g[16];
    for (unsigned di = 0; di < COUNT(dimensions); ++di)
        for (unsigned kv = 1; kv <= 32; ++kv)
            for (unsigned t = 1; t <= 256; ++t) {
                unsigned count = (t - 1) % 16 + 1;
                struct ara_resident_batch b = make_batch(dimensions[di], t, count);
                fill_groups(g, count, kv, 0);
                ++case_id;
                CHECK(ara_resident_batch_header(&b));
                expect_batch(&b, g, kv, 1);
            }
    for (unsigned count = 1; count <= 16; ++count)
        for (unsigned heads = 1; heads <= 8; ++heads)
            for (unsigned di = 0; di < COUNT(dimensions); ++di) {
                struct ara_resident_batch b = make_batch(dimensions[di], 256, count);
                fill_groups(g, count, 32, heads);
                expect_batch(&b, g, 32, 1);
            }
}

#define BAD_BATCH(field, val) do { \
    struct ara_resident_batch bad = base; bad.field = (val); ++case_id; \
    CHECK(!ara_resident_batch_header(&bad)); expect_batch(&bad, g, 32, 0); \
} while (0)

static void batch_boundaries(void)
{
    phase = "batch rejection and boundaries";
    struct ara_resident_batch base = make_batch(96, 7, 16);
    struct ara_resident_batch_group g[16], before[16];
    struct ara_resident_batch_sizes sizes;
    fill_groups(g, 16, 32, 8);
    CHECK(!ara_resident_batch_header(NULL));
    CHECK(!ara_resident_check_batch(NULL, g, 32, &sizes));
    CHECK(!ara_resident_check_batch(&base, NULL, 32, &sizes));
    CHECK(!ara_resident_check_batch(&base, g, 32, NULL));
    expect_batch(&base, g, 0, 0); expect_batch(&base, g, 33, 0);
    expect_batch(&base, g, UINT32_MAX, 0);
    BAD_BATCH(abi, 0); BAD_BATCH(abi, 2); BAD_BATCH(abi, UINT32_MAX);
    BAD_BATCH(bytes, 0); BAD_BATCH(bytes, 96); BAD_BATCH(bytes, 103);
    BAD_BATCH(bytes, 105); BAD_BATCH(bytes, UINT32_MAX);
    BAD_BATCH(count, 0); BAD_BATCH(count, 17); BAD_BATCH(count, UINT32_MAX);
    BAD_BATCH(tokens, 0); BAD_BATCH(tokens, 257); BAD_BATCH(tokens, UINT32_MAX);
    BAD_BATCH(handle, 0);
    BAD_BATCH(groups, 0); BAD_BATCH(query, 0); BAD_BATCH(mask, 0); BAD_BATCH(output, 0);
    for (unsigned d = 0; d <= 512; ++d)
        if (!dimension_ok(d)) { BAD_BATCH(dimension, d); }
    BAD_BATCH(dimension, UINT32_MAX);
    for (unsigned bit = 0; bit < 32; ++bit) {
        BAD_BATCH(flags, UINT32_C(1) << bit); BAD_BATCH(fflags, UINT32_C(1) << bit);
        BAD_BATCH(completed, UINT32_C(1) << bit); BAD_BATCH(reserved0, UINT32_C(1) << bit);
    }
    for (unsigned bit = 0; bit < 64; ++bit)
        for (unsigned i = 0; i < 3; ++i) { BAD_BATCH(reserved[i], UINT64_C(1) << bit); }
    const uint32_t bad_scales[] = {0, 0x3f800001, 0x40000000, 0x7f800000, 0x7f800001,
                                  0x7fc00000, 0x80000000, 0x80000001, 0xbf800000,
                                  0xff800000, 0xffc00000, UINT32_MAX};
    for (unsigned i = 0; i < COUNT(bad_scales); ++i) { BAD_BATCH(scale_bits, bad_scales[i]); }
    const uint32_t good_scales[] = {1, 0x007fffff, 0x00800000, 0x3f000000, 0x3f7fffff, 0x3f800000};
    for (unsigned i = 0; i < COUNT(good_scales); ++i) {
        struct ara_resident_batch b = base;
        b.scale_bits = good_scales[i];
        CHECK(ara_resident_batch_header(&b));
        expect_batch(&b, g, 32, 1);
    }
    for (unsigned offset = 1; offset < 8; ++offset) { BAD_BATCH(groups, base.groups + offset); }
    BAD_BATCH(query, base.query + 1); BAD_BATCH(mask, base.mask + 1);
    for (unsigned offset = 1; offset < 4; ++offset) { BAD_BATCH(output, base.output + offset); }
    /* Header accepts each minimal ABI alignment, not just cache-line addresses. */
    base.groups += 8; base.query += 2; base.mask += 2; base.output += 4;
    base.handle = UINT64_MAX;
    expect_batch(&base, g, 32, 1);
    base.groups = (UINT64_MAX - 16 * 16) & ~UINT64_C(7);
    CHECK(ara_resident_batch_header(&base)); expect_batch(&base, g, 32, 1);
    BAD_BATCH(groups, base.groups + 8);

    for (unsigned di = 0; di < COUNT(dimensions); ++di) {
        base = make_batch(dimensions[di], 256, 16);
        fill_groups(g, 16, 32, 8);
        CHECK(batch_oracle(&base, g, 32, &sizes));
        base.query = (UINT64_MAX - sizes.query) & ~UINT64_C(1);
        base.mask = (UINT64_MAX - sizes.mask) & ~UINT64_C(1);
        base.output = (UINT64_MAX - sizes.output) & ~UINT64_C(3);
        expect_batch(&base, g, 32, 1);
        struct ara_resident_batch b = base;
        b.query += 2; CHECK(ara_resident_batch_header(&b)); expect_batch(&b, g, 32, 0);
        b = base; b.mask += 2; CHECK(ara_resident_batch_header(&b)); expect_batch(&b, g, 32, 0);
        b = base; b.output += 4; CHECK(ara_resident_batch_header(&b)); expect_batch(&b, g, 32, 0);
    }
    base = make_batch(128, 256, 16);
    fill_groups(g, 16, 32, 8);
    memcpy(before, g, sizeof(g));
    /* Validate every group position, including the sixteenth. Repeated KV heads
     * are legal, and total query heads may exceed the per-group limit of eight. */
    for (unsigned i = 0; i < 16; ++i) {
        for (unsigned bit = 0; bit < 64; ++bit) {
            g[i].reserved = UINT64_C(1) << bit;
            expect_batch(&base, g, 32, 0);
        }
        g[i] = before[i];
        g[i].heads = 0; expect_batch(&base, g, 32, 0);
        g[i].heads = 9; expect_batch(&base, g, 32, 0);
        g[i].heads = UINT32_MAX; expect_batch(&base, g, 32, 0);
        g[i] = before[i];
        g[i].kv_head = 32; expect_batch(&base, g, 32, 0);
        g[i].kv_head = UINT32_MAX; expect_batch(&base, g, 32, 0);
        g[i].kv_head = 31; expect_batch(&base, g, 32, 1);
        g[i] = before[i];
    }
    for (unsigned kv = 1; kv <= 32; ++kv) {
        fill_groups(g, 16, kv, 8);
        for (unsigned i = 0; i < 16; ++i) g[i].kv_head = kv - 1;
        expect_batch(&base, g, kv, 1);
        g[15].kv_head = kv; expect_batch(&base, g, kv, 0);
    }
    /* Exact-size arrays make ASan catch reading beyond count, not just past 16. */
    struct ara_resident_batch_group one = {0, 1, 0};
    base = make_batch(64, 1, 1);
    expect_batch(&base, &one, 1, 1);
    base.count = 17;
    expect_batch(&base, &one, 1, 0);
    base.count = 1;
    /* Layout checks do not dereference payload addresses or enforce output aliases. */
    base.query = base.mask = base.output = base.groups;
    expect_batch(&base, &one, 1, 1);
    base.query += 2; base.mask += 4; base.output += 4;
    expect_batch(&base, &one, 1, 1);
}

static void fuzz_views(void)
{
    phase = "deterministic view fuzz";
    for (seed = 0; seed < 4096; ++seed) {
        uint64_t state = seed, k, v, oracle_k = 0, oracle_v = 0;
        unsigned d = dimensions[random64(&state) % 3];
        unsigned h = 1 + random64(&state) % 32, t = 1 + random64(&state) % 256;
        unsigned key_order = random64(&state) & 1;
        unsigned value_order = random64(&state) & 1;
        unsigned gap = (random64(&state) % 8) * 64;
        unsigned block_gap = (random64(&state) % 8) * 64;
        struct ara_resident_kv_view base = make_view(d, h, t, key_order,
                value_order, gap, block_gap, &k, &v);
        ++case_id;
        int valid = k <= ARA_RESIDENT_MAX_VIEW_BYTES && v <= ARA_RESIDENT_MAX_VIEW_BYTES;
        CHECK(view_oracle(&base, &oracle_k, &oracle_v) == valid);
        if (valid) { CHECK(k == oracle_k); CHECK(v == oracle_v); }
        expect_view(&base, valid, k, v);
        /* Always include a valid payload per seed, then isolated invalid mutations. */
        key_order = random64(&state) & 1;
        value_order = random64(&state) & 1;
        base = make_view(d, 1 + h % 8, 1 + t % 16, key_order, value_order, 64, 128, &k, &v);
        expect_view(&base, 1, k, v);
        BAD_VIEW(flags, (uint32_t)random64(&state) | 1u);
        BAD_VIEW(handle, random64(&state) | 1);
        BAD_VIEW(reserved[seed % 4], random64(&state) | 1);
        BAD_VIEW(key, base.key + 1 + random64(&state) % 63);
        BAD_VIEW(value_token_stride, base.value_token_stride + 1);
        /* Small arbitrary stride pairs: walk both orders independently. */
        base.kv_heads = 1 + random64(&state) % 8;
        base.capacity = 1 + random64(&state) % 16;
        base.key_token_stride = (random64(&state) % 96) * 64;
        base.key_head_stride = (random64(&state) % 96) * 64;
        base.value_token_stride = (random64(&state) % 96) * 64;
        base.value_head_stride = (random64(&state) % 96) * 64;
        valid = view_oracle(&base, &oracle_k, &oracle_v);
        expect_view(&base, valid, oracle_k, oracle_v);
        uint64_t extent = 0;
        valid = extent_oracle(d, base.kv_heads, base.capacity,
                             base.key_token_stride, base.key_head_stride, &extent);
        expect_extent(d, base.kv_heads, base.capacity, base.key_token_stride,
                      base.key_head_stride, valid, extent);
    }
    seed = 0;
}

static void fuzz_batches(void)
{
    phase = "deterministic batch fuzz";
    for (seed = 0; seed < 4096; ++seed) {
        uint64_t state = seed ^ UINT64_C(0x66229420e153a71f);
        unsigned kv = 1 + random64(&state) % 32;
        unsigned d = dimensions[random64(&state) % 3];
        unsigned tokens = 1 + random64(&state) % 256;
        unsigned count = 1 + random64(&state) % 16;
        struct ara_resident_batch b = make_batch(d, tokens, count);
        struct ara_resident_batch_group g[16], before[16];
        memset(g, 0, sizeof(g));
        for (unsigned i = 0; i < b.count; ++i) {
            g[i].heads = 1 + random64(&state) % 8;
            g[i].kv_head = random64(&state) % kv;
        }
        b.handle = random64(&state) | 1;
        b.scale_bits = 1 + random64(&state) % UINT32_C(0x3f800000);
        ++case_id;
        expect_batch(&b, g, kv, 1);
        unsigned index = random64(&state) % b.count;
        memcpy(before, g, sizeof(g));
        g[index].heads = 9 + random64(&state) % 100;
        expect_batch(&b, g, kv, 0);
        g[index] = before[index]; g[index].kv_head = kv + random64(&state) % 64;
        expect_batch(&b, g, kv, 0);
        g[index] = before[index]; g[index].reserved = random64(&state) | 1;
        expect_batch(&b, g, kv, 0);
        memcpy(g, before, sizeof(g));
        b.scale_bits = (uint32_t)random64(&state);
        CHECK(!!ara_resident_batch_header(&b) == header_oracle(&b));
        expect_batch(&b, g, kv, header_oracle(&b));
        /* High-bit addresses exercise end overflow without dereferencing memory. */
        b.scale_bits = 0x3f800000;
        b.query = (UINT64_MAX - random64(&state) % 65536) & ~UINT64_C(1);
        b.mask = (UINT64_MAX - random64(&state) % 1024) & ~UINT64_C(1);
        b.output = (UINT64_MAX - random64(&state) % 131072) & ~UINT64_C(3);
        b.groups = (UINT64_MAX - random64(&state) % 512) & ~UINT64_C(7);
        struct ara_resident_batch_sizes sizes;
        CHECK(!!ara_resident_batch_header(&b) == header_oracle(&b));
        expect_batch(&b, g, kv, batch_oracle(&b, g, kv, &sizes));
        CHECK(memcmp(g, before, sizeof(g)) == 0);
    }
    seed = 0;
}

static void expect_overlap(uint64_t a, uint64_t na, uint64_t b, uint64_t nb)
{
    int expected = overlap_oracle(a, na, b, nb);
    int actual = !!ara_resident_ranges_overlap(a, na, b, nb);
    int reverse = !!ara_resident_ranges_overlap(b, nb, a, na);
    if ((actual != expected || reverse != expected) && failures < 32)
        fprintf(stderr, "ranges a=%" PRIu64 " bytes=%" PRIu64 " b=%" PRIu64
                " bytes=%" PRIu64 " expected=%d actual=%d reverse=%d\n",
                a, na, b, nb, expected, actual, reverse);
    CHECK(actual == expected);
    CHECK(reverse == expected);
}

static void overlap_tests(void)
{
    phase = "byte-range overlap";
    expect_overlap(64, 64, 128, 64); /* touching */
    expect_overlap(64, 65, 128, 64); /* one-byte overlap */
    expect_overlap(64, 64, 64, 64);  /* exact alias */
    expect_overlap(64, 128, 65, 1); /* containment */
    expect_overlap(0, UINT64_MAX, UINT64_MAX, 1);
    expect_overlap(0, UINT64_MAX, UINT64_MAX - 1, 1);
    expect_overlap(UINT64_MAX - 63, 64, UINT64_MAX, 1);
    expect_overlap(UINT64_MAX - 63, 63, UINT64_MAX, 1);
    expect_overlap(UINT64_MAX, UINT64_MAX, 0, UINT64_MAX);
    expect_overlap(UINT64_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX);
    /* Empty intervals never overlap, even when their base aliases live bytes. */
    expect_overlap(64, 64, 64, 0);
    expect_overlap(64, 64, 65, 0);
    expect_overlap(64, 0, 64, 0);
    expect_overlap(UINT64_MAX, 1, UINT64_MAX, 0);
    const uint64_t edges[] = {0, 1, 2, 63, 64, 65, 127, 128, 129,
                             UINT64_MAX - 128, UINT64_MAX - 64, UINT64_MAX - 1, UINT64_MAX};
    const uint64_t lengths[] = {0, 1, 2, 63, 64, 65, 128, UINT64_MAX};
    for (unsigned a = 0; a < COUNT(edges); ++a)
        for (unsigned b = 0; b < COUNT(edges); ++b)
            for (unsigned na = 0; na < COUNT(lengths); ++na)
                for (unsigned nb = 0; nb < COUNT(lengths); ++nb) {
                    ++case_id;
                    expect_overlap(edges[a], lengths[na], edges[b], lengths[nb]);
                }
    phase = "deterministic byte-range fuzz";
    for (seed = 0; seed < 4096; ++seed) {
        uint64_t state = seed ^ UINT64_C(0x530bda3e488f19ae);
        for (unsigned trial = 0; trial < 16; ++trial) {
            uint64_t a = random64(&state), b = random64(&state);
            uint64_t na = random64(&state), nb = random64(&state);
            ++case_id;
            expect_overlap(a, na, b, nb);
            /* Nearby intervals prevent almost all generated pairs being disjoint. */
            a &= UINT64_MAX - 4095;
            b = a + random64(&state) % 2048;
            na = random64(&state) % 2048;
            nb = random64(&state) % 2048;
            expect_overlap(a, na, b, nb);
        }
    }
    seed = 0;
}

static void run_section(void (*test)(void), const char *name)
{
    uint64_t start_checks = checks, start_failures = failures;
    test();
    printf("%s %s: checks=%" PRIu64 " failures=%" PRIu64 "\n",
           failures == start_failures ? "PASS" : "FAIL", name,
           checks - start_checks, failures - start_failures);
}

int main(void)
{
    run_section(sweep_views, "view shape sweep");
    run_section(view_boundaries, "view boundaries");
    run_section(sweep_batches, "batch shape sweep");
    run_section(batch_boundaries, "batch boundaries");
    run_section(fuzz_views, "view fuzz");
    run_section(fuzz_batches, "batch fuzz");
    run_section(overlap_tests, "overlap edges and fuzz");
    printf("%s layout HOST: checks=%" PRIu64 " failures=%" PRIu64
           "; D64/96/128 KV-heads=1..32 capacity=1..256 groups=1..16"
           "; 4096 deterministic seeds per fuzz family; ABI view=96 batch=104 release=32\n",
           failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
}
