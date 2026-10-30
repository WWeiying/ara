#include "software/akv/experimental/quantized_kv/ggml_memory.h"
#include "ggml-alloc.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cfenv>
#include <cstdio>
#include <cstring>
#include <limits>
#include <initializer_list>

static unsigned accepted,rejected;

static void rejected_extent(ggml_tensor tensor) {
    size_t bytes=12345;
    assert(!akv_quant_ggml_host_extent(&tensor,&bytes));
    assert(bytes==12345);
    ++rejected;
}

static void run(unsigned dim,unsigned group,unsigned heads,unsigned capacity,unsigned q4) {
    ggml_init_params params{};
    params.mem_size=2*1024*1024; params.no_alloc=true;
    ggml_context *ctx=ggml_init(params);
    assert(ctx);
    ggml_tensor *q=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,dim,1,group*heads,1);
    ggml_tensor *k=ggml_new_tensor_4d(ctx,q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,dim,capacity,heads,1);
    // A real nonzero-offset view with a gap between KV heads.
    ggml_tensor *parent=ggml_new_tensor_4d(ctx,GGML_TYPE_Q8_0,dim,capacity+2,heads,1);
    ggml_tensor *v=ggml_view_4d(ctx,parent,dim,capacity,heads,1,parent->nb[1],parent->nb[2],parent->nb[3],parent->nb[1]);
    ggml_tensor *mask=ggml_new_tensor_4d(ctx,GGML_TYPE_F16,capacity,1,1,1);
    ggml_tensor *dst=ggml_flash_attn_ext(ctx,q,k,v,mask,0.125f,0,0);
    ggml_backend_buffer_t buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,ggml_backend_cpu_buffer_type());
    assert(buffer && ggml_backend_buffer_is_host(buffer));
    ggml_backend_buffer_clear(buffer,0);
    const unsigned visible=capacity==33 ? 31 : 65;
    auto *mask_words=static_cast<uint16_t *>(mask->data);
    for(unsigned i=0;i<capacity;++i) mask_words[i]=i<visible ? 0 : UINT16_C(0xfc00);
    std::memset(dst->data,0xa5,ggml_nbytes(dst));
    qbs_device_t device{};
    assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
    akv_quant_ggml_context_t input{},checked{};
    input.requested=1; input.nth=1; input.vlen_bits=1024; input.device=&device;
    input.normal_memory=1; // This test owns an ordinary CPU heap allocation.
    assert(akv_quant_ggml_memory_context(dst,&input,&checked));
    assert(checked.query_bytes==ggml_nbytes(q) && checked.key_bytes==ggml_nbytes(k));
    assert(checked.value_bytes==ggml_nbytes(v) && checked.mask_bytes==ggml_nbytes(mask));
    assert(checked.output_bytes==ggml_nbytes(dst));
    assert(checked.normal_memory==input.normal_memory);
    akv_quant_selection_input_t mapped{};
    akv_quant_selection_t selection{};
    assert(akv_quant_ggml_map(dst,&checked,&mapped)==AKV_QUANT_GGML_MAP_OK);
    assert(akv_quant_select(&mapped,&selection)==AKV_QUANT_SELECT_OK);
    assert(selection.visible_tokens==visible && selection.group_heads==group && selection.kv_heads==heads);
    for(size_t i=0;i<ggml_nbytes(dst);++i) assert(static_cast<unsigned char *>(dst->data)[i]==0xa5);
    // Returning allocation remainders would cause these disjoint tensors in
    // one actual backend buffer to fail the selector's alias checks above.
    assert(checked.query_bytes<ggml_backend_buffer_get_size(buffer));
    ++accepted;
    ggml_tensor bad=*q;
    bad.data=static_cast<char *>(ggml_backend_buffer_get_base(buffer))+ggml_backend_buffer_get_size(buffer)-1;
    rejected_extent(bad);
    bad=*q; bad.data=reinterpret_cast<void *>(reinterpret_cast<uintptr_t>(ggml_backend_buffer_get_base(buffer))-1);
    rejected_extent(bad);
    bad=*q; bad.ne[3]=2; bad.nb[3]=std::numeric_limits<size_t>::max(); rejected_extent(bad);
    bad=*q; bad.ne[0]=0; rejected_extent(bad);
    bad=*q; bad.type=GGML_TYPE_I32; rejected_extent(bad);
    bad=*v; bad.ne[0]=dim-1; rejected_extent(bad);
    bad=*v; bad.buffer=nullptr;
    size_t bytes=0;
    assert(akv_quant_ggml_host_extent(&bad,&bytes) && bytes==ggml_nbytes(v));
    bad=*q; bad.buffer=nullptr; bad.view_src=&bad; rejected_extent(bad);
    ggml_tensor *saved=dst->src[1]; dst->src[1]=&bad;
    akv_quant_ggml_context_t before{};
    std::memset(&checked,0xa5,sizeof(checked)); std::memcpy(&before,&checked,sizeof(before));
    assert(!akv_quant_ggml_memory_context(dst,&input,&checked));
    assert(!std::memcmp(&checked,&before,sizeof(before)));
    dst->src[1]=saved;
    input.normal_memory=0;
    assert(akv_quant_ggml_memory_context(dst,&input,&checked) && checked.normal_memory==0);
    assert(akv_quant_ggml_map(dst,&checked,&mapped)==AKV_QUANT_GGML_MAP_OK);
    assert(akv_quant_select(&mapped,&selection)==AKV_QUANT_SELECT_CAPABILITY);
    ggml_backend_buffer_free(buffer); ggml_free(ctx);
}

int main() {
    for(unsigned d : {32u,128u,256u})
        for(unsigned group : {1u,3u,6u,8u})
            for(unsigned heads : {1u,2u})
                for(unsigned capacity : {33u,128u})
                    for(unsigned q4 : {0u,1u}) run(d,group,heads,capacity,q4);
    std::printf("GGML_REAL_MEMORY_PASS accepted=%u rejected=%u actual_allocator=1 nonzero_view=1 same_buffer=1 output_untouched=1 execution=0\n",accepted,rejected);
}
