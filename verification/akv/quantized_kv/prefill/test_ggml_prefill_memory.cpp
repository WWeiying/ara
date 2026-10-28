#include "ggml_map.h"
#include "software/akv/experimental/quantized_kv/ggml_memory.h"
#include "ggml-alloc.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

static unsigned accepted, rejected;

static void run(unsigned dim, unsigned queries, unsigned gqa, bool q4) {
    ggml_init_params params{};
    params.mem_size = 2*1024*1024; params.no_alloc = true;
    auto *ctx = ggml_init(params); assert(ctx);
    const unsigned heads = 2, capacity = 64, mask_rows = (queries+31)/32*32;
    auto *qp = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, dim, queries+2, gqa*heads, 1);
    auto *q = ggml_view_4d(ctx, qp, dim, queries, gqa*heads, 1,
                          qp->nb[1], qp->nb[2], qp->nb[3], qp->nb[1]);
    auto *kp = ggml_new_tensor_4d(ctx, q4?GGML_TYPE_Q4_0:GGML_TYPE_Q8_0,
                                 dim, capacity+2, heads, 1);
    auto *k = ggml_view_4d(ctx, kp, dim, capacity, heads, 1,
                          kp->nb[1], kp->nb[2], kp->nb[3], kp->nb[1]);
    auto *vp = ggml_new_tensor_4d(ctx, GGML_TYPE_Q8_0, dim, capacity+2, heads, 1);
    auto *v = ggml_view_4d(ctx, vp, dim, capacity, heads, 1,
                          vp->nb[1], vp->nb[2], vp->nb[3], vp->nb[1]);
    auto *mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, capacity, mask_rows, 1, 1);
    auto *dst = ggml_flash_attn_ext(ctx, q, k, v, mask, 0.125f, 0, 0);
    auto buffer = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
    assert(buffer); ggml_backend_buffer_clear(buffer, 0);
    auto *words = static_cast<uint16_t *>(mask->data);
    for(unsigned row=0; row<mask_rows; ++row)
        for(unsigned token=0; token<capacity; ++token)
            words[row*capacity+token] = token<row+1 ? 0 : 0xfc00;
    std::memset(dst->data, 0xa5, ggml_nbytes(dst));
    qbs_device_t device{};
    assert(qbs_device_init_reference(1024, &device)==QBS_STATUS_OK);
    akv_quant_ggml_context_t context{}, checked{};
    context.requested=1; context.nth=1; context.normal_memory=1;
    context.vlen_bits=1024; context.device=&device;
    assert(akv_quant_ggml_memory_context(dst, &context, &checked));
    assert(checked.query_bytes==ggml_nbytes(q) && checked.key_bytes==ggml_nbytes(k));
    assert(checked.value_bytes==ggml_nbytes(v) && checked.mask_bytes==ggml_nbytes(mask));
    assert(checked.output_bytes==ggml_nbytes(dst));
    quant_prefill_input_t mapped{};
    quant_prefill_admission_t plan{};
    assert(quant_prefill_ggml_map(dst, &checked, &mapped)==AKV_QUANT_GGML_MAP_OK);
    assert(quant_prefill_admit(&mapped, &plan)==AKV_QUANT_SELECT_OK);
    assert(plan.queries==queries && plan.common.group_heads==gqa && plan.common.kv_heads==heads);
    assert(plan.common.visible_tokens==queries);
    for(unsigned row=0; row<queries; ++row) assert(plan.visible[row]==row+1);
    ++accepted;

    // A hole in only the last active query must reject before any execution.
    auto before = plan;
    words[(queries-1)*capacity]=0xfc00;
    assert(quant_prefill_admit(&mapped, &plan)==AKV_QUANT_SELECT_MASK);
    assert(!std::memcmp(&plan, &before, sizeof(plan))); ++rejected;
    words[(queries-1)*capacity]=0;

    // The views share one allocation but do not alias; an actual alias must fail.
    auto bad = mapped;
    bad.tensors.output.data = mapped.tensors.query.data;
    assert(quant_prefill_admit(&bad, &plan)==AKV_QUANT_SELECT_ALIAS); ++rejected;
    auto bad_tensor = *q;
    bad_tensor.data = static_cast<char *>(ggml_backend_buffer_get_base(buffer))+
                      ggml_backend_buffer_get_size(buffer)-1;
    size_t extent=123;
    assert(!akv_quant_ggml_host_extent(&bad_tensor, &extent) && extent==123); ++rejected;
    for(size_t i=0; i<ggml_nbytes(dst); ++i)
        assert(static_cast<unsigned char *>(dst->data)[i]==0xa5);
    ggml_backend_buffer_free(buffer); ggml_free(ctx);
}

int main() {
    for(unsigned d : {32u, 128u, 256u})
        for(unsigned q : {2u, 20u, 33u})
            for(unsigned g : {2u, 3u, 6u})
                for(bool q4 : {false, true}) run(d,q,g,q4);
    std::printf("PREFILL_REAL_MEMORY_PASS accepted=%u rejected=%u actual_allocator=1 nonzero_views=1 execution=0\n", accepted,rejected);
}
