#include "kernel_compute.h"
#include "finite_f16.h"

/* Linux defines noinline as a macro; the SDK uses the GCC attribute token. */
#ifdef noinline
#undef noinline
#endif

/* Sources are extracted with git archive into the build directory. Including
 * the real SDK core keeps its softmax, F16 rescale and output semantics intact.
 * Section GC retains only the resident path; ordinary attention ASM is absent.
 */
#include "software/akv/src/akv_v2_native_riscv.c"

#define ARA_EINVAL 22
#define ARA_EIO 5
#define ARA_EOPNOTSUPP 95

struct __attribute__((aligned(64))) ara_compute_scratch {
    akv_device_t device;
    akv_attention_plan_t plan;
    akv_attention_v2_workspace_t workspace;
    akv_resident_attention_options_t options;
    resident_schedule_t schedule;
};

__attribute__((externally_visible)) size_t ara_resident_compute_scratch_bytes(void)
{
    return sizeof(struct ara_compute_scratch);
}

static int span_valid(const void *pointer, size_t bytes)
{
    return pointer != NULL && bytes != 0 &&
           (uintptr_t)pointer <= UINTPTR_MAX - bytes;
}

static int spans_overlap(const void *left, size_t left_bytes,
                         const void *right, size_t right_bytes)
{
    return (uintptr_t)left < (uintptr_t)right + right_bytes &&
           (uintptr_t)right < (uintptr_t)left + left_bytes;
}

static int validate_buffers(const struct ara_resident_compute_buffers *b)
{
    size_t q_bytes, k_bytes, v_bytes, mask_bytes, out_bytes;
    const void *spans[6];
    size_t lengths[6];
    unsigned i;

    if (b->heads < 1 || b->heads > 8 ||
        !(b->dimension == 64 || b->dimension == 96 || b->dimension == 128) ||
        b->tokens < 1 || b->tokens > 256 ||
        (b->flags & ~ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS) ||
        b->resident_used != 0 ||
        b->scratch_bytes < ara_resident_compute_scratch_bytes() ||
        (((uintptr_t)b->query | (uintptr_t)b->key | (uintptr_t)b->value |
          (uintptr_t)b->scratch) & 63u) ||
        ((uintptr_t)b->mask & 1u) || ((uintptr_t)b->output & 3u) ||
        (b->scale_bits & 0x80000000u) || b->scale_bits == 0 ||
        (b->scale_bits & 0x7f800000u) == 0x7f800000u)
        return -ARA_EINVAL;

    const size_t row = b->dimension * 2u;
    const size_t ks = b->key_token_stride ? b->key_token_stride : row;
    const size_t vs = b->value_token_stride ? b->value_token_stride : row;
    if (ks < row || vs < row || ((ks | vs) & 63u) ||
        ks > 1024u * 1024u || vs > 1024u * 1024u)
        return -ARA_EINVAL;

    q_bytes = (size_t)b->heads * b->dimension * 2u;
    k_bytes = (b->tokens - 1u) * ks + row;
    v_bytes = (b->tokens - 1u) * vs + row;
    mask_bytes = (size_t)b->tokens * 2u;
    out_bytes = (size_t)b->heads * b->dimension * 4u;
    spans[0] = b->query; lengths[0] = q_bytes;
    spans[1] = b->key; lengths[1] = k_bytes;
    spans[2] = b->value; lengths[2] = v_bytes;
    spans[3] = b->mask; lengths[3] = mask_bytes;
    spans[4] = b->output; lengths[4] = out_bytes;
    spans[5] = b->scratch; lengths[5] = b->scratch_bytes;
    for (i = 0; i != 6; ++i) {
        if (!span_valid(spans[i], lengths[i]) ||
            spans_overlap(b, sizeof(*b), spans[i], lengths[i]))
            return -ARA_EINVAL;
    }
    for (i = 0; i != 5; ++i)
        if (spans_overlap(b->scratch, b->scratch_bytes, spans[i], lengths[i]))
            return -ARA_EINVAL;
    for (i = 0; i != 4; ++i)
        if (spans_overlap(b->output, out_bytes, spans[i], lengths[i]))
            return -ARA_EINVAL;
    return 0;
}

static int validate_domain(const struct ara_resident_compute_buffers *b)
{
    const uint16_t *q = b->query, *k = b->key, *v = b->value, *mask = b->mask;
    unsigned visible = 0;

    /* Finite F16 dot <= 128*65504^2 < 2^40, scale <= 1, |mask| <= 65504.
     * Scores and their differences cannot overflow F32; old_max-new_max <= 0.
     * This gate does not change the SDK's existing F16 PV accumulator rounding.
     */
    if (b->scale_bits > 0x3f800000u)
        return -ARA_EOPNOTSUPP;
    if (!ara_resident_finite_f16(q, (size_t)b->heads * b->dimension))
        return -ARA_EOPNOTSUPP;
    const size_t ks = b->key_token_stride ? b->key_token_stride / 2 : b->dimension;
    const size_t vs = b->value_token_stride ? b->value_token_stride / 2 : b->dimension;
    if (ks == b->dimension && vs == b->dimension) {
        if (!ara_resident_finite_f16(k, (size_t)b->tokens * b->dimension) ||
            !ara_resident_finite_f16(v, (size_t)b->tokens * b->dimension)) return -ARA_EOPNOTSUPP;
    } else {
        for (unsigned t = 0; t < b->tokens; ++t)
            if (!ara_resident_finite_f16(k + t * ks, b->dimension) ||
                !ara_resident_finite_f16(v + t * vs, b->dimension)) return -ARA_EOPNOTSUPP;
    }
    for (unsigned i = 0; i < b->tokens; ++i) {
        if ((mask[i] & 0x7c00u) != 0x7c00u)
            visible = 1;
        else if (mask[i] != 0xfc00u)
            return -ARA_EOPNOTSUPP;
    }
    return visible ? 0 : -ARA_EOPNOTSUPP;
}

/* This is pure preparation after trap-safe discovery, before workspace/FULL. */
static int prepare_compute(struct ara_resident_compute_buffers *b,
                           struct ara_compute_scratch *s,
                           uintptr_t vlenb, uintptr_t frm, uintptr_t vstart)
{
    const akv_capabilities_t *c = &s->device.capabilities;
    akv_attention_problem_t problem = {0};
    akv_status_t status;

    if (!c->resident_valid || !c->resident_qk_supported ||
        !c->resident_pv_supported ||
        c->resident_capability_version != AKV_RESIDENT_CAPABILITY_VERSION ||
        c->resident_nr_lanes != 4 || c->resident_vlen_bits != 1024 ||
        vlenb != 128 || frm != 0 || vstart != 0)
        return -ARA_EOPNOTSUPP;

    problem.query = b->query;
    problem.key = b->key;
    problem.value = b->value;
    problem.mask = b->mask;
    problem.output = b->output;
    problem.q_row_stride_bytes = b->dimension * 2u;
    problem.k_token_stride_bytes = b->key_token_stride ? b->key_token_stride : b->dimension * 2u;
    problem.v_token_stride_bytes = b->value_token_stride ? b->value_token_stride : b->dimension * 2u;
    problem.output_row_stride_bytes = b->dimension * 4u;
    problem.q_rows = b->heads;
    problem.head_dim = b->dimension;
    problem.kv_length = b->tokens;
    memcpy(&problem.scale, &b->scale_bits, sizeof(problem.scale));
    status = akv_attention_plan_create_v2(&s->device, &problem, &s->plan);
    if (status != AKV_STATUS_OK)
        return status == AKV_STATUS_CAPABILITY || status == AKV_STATUS_SHAPE ||
               status == AKV_STATUS_RUNTIME_UNAVAILABLE
                   ? -ARA_EOPNOTSUPP : -ARA_EINVAL;

    s->options = (akv_resident_attention_options_t){
        .requested = 1,
        .validated_available = !!(b->flags & ARA_RESIDENT_COMPUTE_VALIDATED_AVAILABLE),
        .platform_admitted = !!(b->flags & ARA_RESIDENT_COMPUTE_PLATFORM_ADMITTED),
        .whole_call_owned = !!(b->flags & ARA_RESIDENT_COMPUTE_WHOLE_CALL_OWNED),
        .decode_head_rows = 1, .query_tokens = 1, .plain_scores = 1,
        .vlenb = vlenb, .frm = (unsigned)frm, .vstart = vstart,
    };
    if (!prepare_resident_schedule(&s->device, &s->plan, &s->options,
                                   NULL, 0, &s->schedule))
        return -ARA_EOPNOTSUPP;
    return 0;
}

#if defined(__riscv) && defined(__riscv_vector) && defined(__riscv_zvfh)
static uint64_t compute_info(void *unused, unsigned index)
{
    register uintptr_t a0 __asm__("a0") = index;
    (void)unused;
    __asm__ volatile(".word 0x0005455b" : "+r"(a0) : : "memory");
    return a0;
}
#endif

int ara_resident_compute_owned(struct ara_resident_compute_buffers *b);

__attribute__((externally_visible, visibility("hidden")))
int ara_resident_compute_owned(struct ara_resident_compute_buffers *b)
{
    struct ara_compute_scratch *s;
    int result;
    if (b == NULL)
        return -ARA_EINVAL;
    if (b->started != 0)
        return -ARA_EIO;
    result = validate_buffers(b);
    if (result)
        return result;
    if (b->flags != ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS)
        return -ARA_EOPNOTSUPP;
    result = validate_domain(b);
    if (result)
        return result;
    s = b->scratch;

#if defined(__riscv) && defined(__riscv_vector) && defined(__riscv_zvfh)
    uintptr_t vlenb, frm, vstart;
    /* The scalar entry already installed the scope-owned ABI state. */
    __asm__ volatile("csrr %0, vlenb\ncsrr %1, frm\ncsrr %2, vstart"
                     : "=r"(vlenb), "=r"(frm), "=r"(vstart) : : "memory");
    if (vlenb != 128 || frm != 0 || vstart != 0)
        return -ARA_EOPNOTSUPP;
    if (akv_device_query(compute_info, NULL, &s->device) != AKV_STATUS_OK)
        return -ARA_EOPNOTSUPP;
    result = prepare_compute(b, s, vlenb, frm, vstart);
    if (result)
        return result;

    /* The route is now frozen. No native fallback and no post-FULL admission. */
    b->started = 1;
    __asm__ volatile("" : : : "memory");
    initialize_workspace(&s->workspace, b->heads, b->dimension);
    for (unsigned start = 0; start < b->tokens; start += AKV_V2_TILE_TOKENS) {
        unsigned count = akv_v2_tile_length(b->tokens, start);
        const akv_resident_attention_tile_t *tile =
            count == s->schedule.full.tokens ? &s->schedule.full : &s->schedule.tail;
        if (start == 0)
            issue_full(&s->plan.descriptor, 0);
        else
            issue_refill(start);
        resident_qk_tile(tile, &s->workspace);
        apply_scale_mask_and_softmax(s->plan.mask, s->plan.scale, &s->workspace,
                                     start, count, b->heads, NULL);
        resident_pv_tile(tile, &s->workspace);
    }
    issue_release();
    store_outputs(b->output, s->plan.output_row_stride_bytes,
                   &s->workspace, b->heads, b->dimension);
    __asm__ volatile("csrr %0, fflags" : "=r"(b->flags) : : "memory");
    b->resident_used = 1;
    return 0;
#else
    (void)s;
    return -ARA_EOPNOTSUPP;
#endif
}
