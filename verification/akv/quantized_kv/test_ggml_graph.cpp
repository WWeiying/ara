#include "software/akv/experimental/quantized_kv/ggml_entry.h"
#include "verification/qbs/qbs_ref.h"
#include "ggml-alloc.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

extern "C" void quant_kv_ggml_mad_f32(int,float *,const float *,float);
extern "C" void quant_kv_ggml_scale_f32(int,float *,float);
static unsigned commands,quantizes,decodes,fail_at;

static std::vector<unsigned char> load(const std::string &path,size_t bytes) {
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    assert(file && file.tellg()==static_cast<std::streamoff>(bytes));
    file.seekg(0);
    std::vector<unsigned char> result(bytes);
    file.read(reinterpret_cast<char *>(result.data()),bytes);
    assert(file.good()); return result;
}

static void quantize(const float *x,void *y,int64_t n) {
    ++quantizes;
    ggml_get_type_traits_cpu(GGML_TYPE_Q8_0)->from_float(x,y,n);
}
static void decode(const void *x,float *y,int64_t n) {
    ++decodes;
    ggml_get_type_traits(GGML_TYPE_Q8_0)->to_float(x,y,n);
}

static qbs_status_t execute(void *,const qbs_descriptor_t *desc,unsigned m,const void *activation,
    float *output,size_t stride,unsigned n,int segmented) {
    ++commands;
    if(fail_at && commands==fail_at) return QBS_STATUS_EXECUTION;
    const auto fields=qbs_unpack_descriptor_header(desc->header);
    assert(!segmented && fields.activation_access==QBS_ACTIVATION_ACCESS_DIRECT && m<=4 && n==32);
    const size_t weight_row=fields.k_blocks*(fields.weight_profile==QBS_WEIGHT_PROFILE_Q4_0 ? 18u : 34u);
    float registers[128]{};
    qbs_ref_result_t result{};
    fenv_t previous;
    assert(std::fegetenv(&previous)==0);
    const auto status=qbs_ref_execute(desc,m,8,1024,reinterpret_cast<uintptr_t>(activation),
        reinterpret_cast<const void *>(static_cast<uintptr_t>(desc->weight_base)),n*weight_row,
        activation,m*fields.k_blocks*34,registers,128,nullptr,nullptr,&result);
    // The scalar command oracle clears host exceptions internally. Restore
    // caller rounding/sticky state while merging this command's exceptions.
    assert(std::feupdateenv(&previous)==0);
    assert(status==QBS_REF_OK && result.active_outputs==m*n);
    for(unsigned row=0;row<m;++row) std::memcpy(output+row*stride,registers+row*32,n*4);
    return QBS_STATUS_OK;
}

static float compare(const float *x,const float *y,size_t n) {
    float maximum=0;
    for(size_t i=0;i<n;++i) {
        assert(std::isfinite(x[i]) && std::isfinite(y[i]));
        const float delta=std::fabs(x[i]-y[i]);
        assert(delta<=0.004f+0.002f*std::fabs(y[i]));
        if(delta>maximum) maximum=delta;
    }
    return maximum;
}

int main(int argc,char **argv) {
    assert(argc==3 && (std::string(argv[1])=="q8_0" || std::string(argv[1])=="q4_0"));
    const bool q4=std::string(argv[1])=="q4_0";
    const std::string dir=argv[2];
    ggml_cpu_init();
    assert(ggml_get_type_traits_cpu(GGML_TYPE_Q8_0)->from_float &&
           ggml_get_type_traits(GGML_TYPE_Q8_0)->to_float);
    ggml_init_params init{}; init.mem_size=4*1024*1024; init.no_alloc=true;
    ggml_context *ctx=ggml_init(init); assert(ctx);
    auto *q=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,128,1,12,1);
    auto *k=ggml_new_tensor_4d(ctx,q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,128,256,2,1);
    auto *v=ggml_new_tensor_4d(ctx,GGML_TYPE_Q8_0,128,256,2,1);
    auto *mask=ggml_new_tensor_4d(ctx,GGML_TYPE_F16,256,1,1,1);
    uint32_t scale_word=UINT32_C(0x3db504f3); float scale;
    std::memcpy(&scale,&scale_word,4);
    auto *dst=ggml_flash_attn_ext(ctx,q,k,v,mask,scale,0,0);
    auto *graph=ggml_new_graph(ctx); ggml_build_forward_expand(graph,dst);
    auto buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,ggml_backend_cpu_buffer_type()); assert(buffer);
    const ggml_tensor *tensors[]={q,k,v,mask};
    const char *names[]={"attn_q_input-0.bin","attn_k_input-0.bin","attn_v_input-0.bin","attn_mask_input-0.bin"};
    for(unsigned i=0;i<4;++i) {
        auto bytes=load(dir+"/"+names[i],ggml_nbytes(tensors[i]));
        ggml_backend_tensor_set(const_cast<ggml_tensor *>(tensors[i]),bytes.data(),0,bytes.size());
    }
    const auto golden_bytes=load(dir+"/kqv_out-0.bin",6144);
    std::vector<float> golden(1536),ordinary(1536),candidate(1536);
    std::memcpy(golden.data(),golden_bytes.data(),6144);
    assert(ggml_graph_compute_with_ctx(ctx,graph,1)==GGML_STATUS_SUCCESS);
    ggml_backend_tensor_get(dst,ordinary.data(),0,6144);
    const float ordinary_error=compare(ordinary.data(),golden.data(),1536);
    qbs_device_t device{}; assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
    akv_quant_ggml_context_t context{};
    context.requested=1; context.nth=1; context.normal_memory=1;
    context.vlen_bits=1024; context.device=&device;
    const akv_quant_native_bindings_t bindings={quantize,decode,quant_kv_ggml_scale_f32,
        quant_kv_ggml_mad_f32,execute,nullptr};
    const size_t required=akv_quant_native_workspace_bytes();
    std::vector<unsigned char> memory(required+128,0xa5);
    const uintptr_t aligned=(reinterpret_cast<uintptr_t>(memory.data())+63)&~uintptr_t(63);
    void *workspace=reinterpret_cast<void *>(aligned);
    float candidate_error=0,pair_error=0;
    for(unsigned repeat=0;repeat<2;++repeat) {
        std::memset(dst->data,0xa5,6144); commands=quantizes=decodes=0;
        akv_quant_ggml_report_t report{};
        assert(akv_quant_ggml_execute(dst,&context,&bindings,workspace,required,&report)==AKV_QUANT_NATIVE_OK);
        assert(report.mapping_reason==0 && report.memory_verified==1 && report.runtime_called==1 &&
            report.native.completed_groups==2 && report.native.command_attempts==16 &&
            report.native.value_decodes==256 && commands==16 && quantizes==12 && decodes==256);
        auto *actual=static_cast<float *>(dst->data);
        candidate_error=compare(actual,golden.data(),1536);
        pair_error=compare(actual,ordinary.data(),1536);
        if(!repeat) std::memcpy(candidate.data(),actual,6144);
        else assert(!std::memcmp(candidate.data(),actual,6144));
        const size_t first=aligned-reinterpret_cast<uintptr_t>(memory.data());
        for(size_t i=0;i<memory.size();++i)
            if(i<first || i>=first+required) assert(memory[i]==0xa5);
    }
    auto *mask_words=static_cast<uint16_t *>(mask->data);
    const uint16_t old=mask_words[63]; mask_words[63]=UINT16_C(0xfc00);
    std::memset(dst->data,0xa5,6144); commands=quantizes=decodes=0;
    akv_quant_ggml_report_t rejected{};
    assert(akv_quant_ggml_execute(dst,&context,&bindings,workspace,required,&rejected)==AKV_QUANT_NATIVE_FALLBACK);
    assert(rejected.mapping_reason==0 && rejected.memory_verified && rejected.runtime_called &&
           rejected.native.selection_reason==AKV_QUANT_SELECT_MASK && !commands && !quantizes && !decodes);
    for(unsigned i=0;i<6144;++i) assert(static_cast<unsigned char *>(dst->data)[i]==0xa5);
    assert(ggml_graph_compute_with_ctx(ctx,graph,1)==GGML_STATUS_SUCCESS);
    for(unsigned i=0;i<1536;++i) assert(std::isfinite(static_cast<float *>(dst->data)[i]));
    mask_words[63]=old;
    std::memset(dst->data,0xa5,6144); commands=quantizes=decodes=0; fail_at=3;
    assert(akv_quant_ggml_execute(dst,&context,&bindings,workspace,required,&rejected)==AKV_QUANT_NATIVE_EXECUTION_FAILED);
    assert(rejected.runtime_called && rejected.native.executor_status==QBS_STATUS_EXECUTION &&
        rejected.native.completed_groups==0 && rejected.native.command_attempts==3 &&
        commands==3 && quantizes==6 && decodes==32);
    // First KV group's numerator is partial; the untouched second group must
    // not be silently recomputed by an ordinary fallback inside this entry.
    for(unsigned i=3072;i<6144;++i) assert(static_cast<unsigned char *>(dst->data)[i]==0xa5);
    fail_at=0;
    context.requested=0;
    assert(akv_quant_ggml_execute(dst,&context,&bindings,workspace,required,&rejected)==AKV_QUANT_NATIVE_FALLBACK);
    assert(rejected.mapping_reason==AKV_QUANT_GGML_MAP_DISABLED && !rejected.memory_verified && !rejected.runtime_called);
    for(unsigned i=0;i<4;++i) {
        const auto original=load(dir+"/"+names[i],ggml_nbytes(tensors[i]));
        assert(!std::memcmp(tensors[i]->data,original.data(),original.size()));
    }
    std::printf("GGML_QUANT_GRAPH_PASS kind=%s heads=12 kv_heads=2 d=128 visible=128 outputs=1536 repeats=2 commands_per_call=16 decodes_per_call=256 fallback_before_work=1 ordinary_fallback_graph=1 failure_no_retry=1 inputs_unchanged=1 ordinary_gold_max=%.9g candidate_gold_max=%.9g candidate_ordinary_max=%.9g executor=qbs_ref performance=not_measured\n",
        argv[1],static_cast<double>(ordinary_error),static_cast<double>(candidate_error),static_cast<double>(pair_error));
    ggml_backend_buffer_free(buffer); ggml_free(ctx);
}
