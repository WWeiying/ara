/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARA_RESIDENT_VIEW_LAYOUT_H
#define ARA_RESIDENT_VIEW_LAYOUT_H
#include "view_uapi.h"

struct ara_resident_view_sizes { __u32 key, value; };
struct ara_resident_batch_sizes { __u32 heads, query, mask, output, groups; };

static inline int ara_resident_view_extent(__u32 d, __u32 heads, __u32 tokens,
        __u32 token_stride, __u32 head_stride, __u32 *bytes)
{
    __u64 row = (__u64)d * 2, t, h, size;
    if ((token_stride | head_stride) & 63u || token_stride < row || head_stride < row)
        return 0;
    t = (__u64)(tokens - 1) * token_stride + row;
    h = (__u64)(heads - 1) * head_stride + row;
    if (heads > 1 && tokens > 1 && head_stride < t && token_stride < h)
        return 0;
    size = t + (__u64)(heads - 1) * head_stride;
    if (size > ARA_RESIDENT_MAX_VIEW_BYTES) return 0;
    *bytes = (__u32)size;
    return 1;
}

static inline int ara_resident_check_view(const struct ara_resident_kv_view *v,
                                         struct ara_resident_view_sizes *s)
{
    if (!v || !s || v->abi != ARA_RESIDENT_VIEW_ABI || v->bytes != sizeof(*v) ||
        (v->dimension != 64 && v->dimension != 96 && v->dimension != 128) ||
        !v->kv_heads || v->kv_heads > ARA_RESIDENT_MAX_KV_HEADS ||
        !v->capacity || v->capacity > ARA_RESIDENT_MAX_TOKENS || v->flags || v->handle ||
        !v->key || !v->value || (v->key | v->value) & 63u)
        return 0;
    for (unsigned i = 0; i < 4; ++i) if (v->reserved[i]) return 0;
    if (!ara_resident_view_extent(v->dimension, v->kv_heads, v->capacity,
            v->key_token_stride, v->key_head_stride, &s->key) ||
        !ara_resident_view_extent(v->dimension, v->kv_heads, v->capacity,
            v->value_token_stride, v->value_head_stride, &s->value)) return 0;
    return v->key <= ~(__u64)0 - s->key && v->value <= ~(__u64)0 - s->value;
}

static inline int ara_resident_batch_header(const struct ara_resident_batch *b)
{
    if (!b || b->abi != ARA_RESIDENT_VIEW_ABI || b->bytes != sizeof(*b) ||
        !b->count || b->count > ARA_RESIDENT_MAX_BATCH || !b->handle ||
        (b->dimension != 64 && b->dimension != 96 && b->dimension != 128) ||
        !b->tokens || b->tokens > ARA_RESIDENT_MAX_TOKENS ||
        !b->scale_bits || b->scale_bits > 0x3f800000u || b->flags || b->fflags ||
        b->completed || b->reserved0 || !b->groups || !b->query || !b->mask || !b->output ||
        (b->groups & 7u) || ((b->query | b->mask) & 1u) || (b->output & 3u)) return 0;
    for (unsigned i = 0; i < 3; ++i) if (b->reserved[i]) return 0;
    return b->groups <= ~(__u64)0 - b->count * sizeof(struct ara_resident_batch_group);
}

static inline int ara_resident_check_batch(const struct ara_resident_batch *b,
        const struct ara_resident_batch_group *g, unsigned kv_heads,
        struct ara_resident_batch_sizes *s)
{
    unsigned heads = 0;
    if (!g || !s || !kv_heads || kv_heads > ARA_RESIDENT_MAX_KV_HEADS ||
        !ara_resident_batch_header(b)) return 0;
    for (unsigned i = 0; i < b->count; ++i) {
        if (!g[i].heads || g[i].heads > ARA_RESIDENT_MAX_HEADS ||
            g[i].kv_head >= kv_heads || g[i].reserved) return 0;
        heads += g[i].heads;
    }
    s->heads = heads;
    s->query = heads * b->dimension * 2;
    s->mask = b->tokens * 2;
    s->output = heads * b->dimension * 4;
    s->groups = b->count * sizeof(*g);
    return b->query <= ~(__u64)0 - s->query && b->mask <= ~(__u64)0 - s->mask &&
           b->output <= ~(__u64)0 - s->output;
}

static inline int ara_resident_ranges_overlap(__u64 a, __u64 a_bytes, __u64 b, __u64 b_bytes)
{
    if (!a_bytes || !b_bytes) return 0;
    return a <= b ? b - a < a_bytes : a - b < b_bytes;
}
#endif
