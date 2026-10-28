#include "ggml_entry.h"
#include "ggml_map.h"
#include "software/akv/experimental/quantized_kv/ggml_memory.h"
#include "verification/qbs/qbs_ref.h"
#include "ggml-alloc.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" void prefill_host_init(void);
extern "C" void prefill_host_quantize(const float *,void *,int64_t);
extern "C" void prefill_host_decode(const void *,float *,int64_t);
extern "C" void prefill_host_scale(int,float *,float);
extern "C" void prefill_host_mad(int,float *,const float *,float);
static unsigned commands;

static void load(const char *root,const char *name,void *data,size_t bytes) {
    char path[4096];int n=std::snprintf(path,sizeof(path),"%s/%s",root,name);
    assert(n>0 && size_t(n)<sizeof(path));auto *f=std::fopen(path,"rb");assert(f);
    assert(std::fread(data,1,bytes,f)==bytes && std::fgetc(f)==EOF);
    assert(!std::fclose(f));
}
static qbs_status_t reference(void *,const qbs_descriptor_t *desc,unsigned m,
    const void *activation,float *out,size_t stride,unsigned n,int segmented) {
    assert(!segmented && m<=4 && n<=32 && stride>=n);
    auto fields=qbs_unpack_descriptor_header(desc->header);assert(fields.k_blocks==4 && fields.n==n);
    assert(fields.weight_profile==QBS_WEIGHT_PROFILE_Q4_0 || fields.weight_profile==QBS_WEIGHT_PROFILE_Q8_0_WEIGHT);
    size_t block=fields.weight_profile==QBS_WEIGHT_PROFILE_Q4_0?18:34;
    float packed[128];qbs_ref_result_t report;
    assert(qbs_ref_execute(desc,m,8,1024,reinterpret_cast<uintptr_t>(activation),
        reinterpret_cast<const void *>(desc->weight_base),n*4*block,activation,m*136,
        packed,128,nullptr,nullptr,&report)==QBS_REF_OK);
    for(unsigned row=0;row<m;++row) std::memcpy(out+row*stride,packed+row*32,n*4);
    ++commands;return QBS_STATUS_OK;
}

int main(int argc,char **argv) {
    assert(argc==3 && (!std::strcmp(argv[2],"q4_0") || !std::strcmp(argv[2],"q8_0")));
    prefill_host_init();bool q4=!std::strcmp(argv[2],"q4_0");
    ggml_init_params params{};params.mem_size=2*1024*1024;params.no_alloc=true;
    auto *ctx=ggml_init(params);assert(ctx);
    auto *q=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,128,20,16,1);
    auto *k=ggml_new_tensor_4d(ctx,q4?GGML_TYPE_Q4_0:GGML_TYPE_Q8_0,128,256,8,1);
    auto *v=ggml_new_tensor_4d(ctx,GGML_TYPE_Q8_0,128,256,8,1);
    auto *mask=ggml_new_tensor_4d(ctx,GGML_TYPE_F16,256,20,1,1);
    uint32_t bits=0x3db504f3;float scale;std::memcpy(&scale,&bits,4);
    auto *dst=ggml_flash_attn_ext(ctx,q,k,v,mask,scale,0,0);
    auto buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,ggml_backend_cpu_buffer_type());assert(buffer);
    load(argv[1],"attn_q_input-0.bin",q->data,ggml_nbytes(q));
    load(argv[1],"attn_k_input-0.bin",k->data,ggml_nbytes(k));
    load(argv[1],"attn_v_input-0.bin",v->data,ggml_nbytes(v));
    load(argv[1],"attn_mask_input-0.bin",mask->data,ggml_nbytes(mask));
    std::vector<float> golden(40960),baseline(40960);
    load(argv[1],"kqv_out-0.bin",golden.data(),golden.size()*4);
    qbs_device_t device{};assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
    akv_quant_ggml_context_t context{},checked{};
    context.requested=1;context.nth=1;context.normal_memory=1;context.vlen_bits=1024;context.device=&device;
    assert(akv_quant_ggml_memory_context(dst,&context,&checked));
    quant_prefill_input_t mapped{};
    assert(quant_prefill_ggml_map(dst,&checked,&mapped)==AKV_QUANT_GGML_MAP_OK);
    akv_quant_native_bindings_t bindings={prefill_host_quantize,prefill_host_decode,
        prefill_host_scale,prefill_host_mad,reference,nullptr};
    size_t old_bytes=akv_quant_native_workspace_bytes(),bytes=quant_prefill_ggml_workspace_bytes();
    void *old_workspace=std::aligned_alloc(64,old_bytes),*workspace=std::aligned_alloc(64,bytes);
    assert(old_workspace && workspace);
    std::feclearexcept(FE_ALL_EXCEPT);
    for(unsigned t=0;t<20;++t) {
        auto slice=mapped.tensors;
        slice.query.data=static_cast<unsigned char *>(q->data)+t*512;
        slice.query.bytes-=t*512;slice.query.tokens=1;
        slice.output.data=baseline.data()+t*2048;slice.output.bytes-=t*8192;slice.output.tokens=1;
        slice.mask+=t*256;slice.mask_bytes=512;akv_quant_native_report_t report{};
        assert(akv_quant_native_execute(&slice,&bindings,old_workspace,old_bytes,&report)==AKV_QUANT_NATIVE_OK);
    }
    int old_flags=std::fetestexcept(FE_ALL_EXCEPT);assert(commands==160);
    commands=0;std::memset(dst->data,0xa5,ggml_nbytes(dst));std::feclearexcept(FE_ALL_EXCEPT);
    quant_prefill_ggml_report_t report{};
    assert(quant_prefill_ggml_execute(dst,&context,&bindings,workspace,bytes,&report)==AKV_QUANT_NATIVE_OK);
    assert(report.mapping_reason==AKV_QUANT_GGML_MAP_OK && report.memory_verified && report.runtime_called);
    assert(report.native.completed_groups==40 && report.native.command_attempts==160 && commands==160);
    assert(report.native.value_decodes==480 && report.queries_quantized==320);
    assert(std::fetestexcept(FE_ALL_EXCEPT)==old_flags && !std::memcmp(dst->data,baseline.data(),163840));
    double maximum=0;auto *result=static_cast<float *>(dst->data);
    for(unsigned i=0;i<40960;++i) {
        double error=std::fabs(double(result[i])-golden[i]);
        assert(std::isfinite(result[i]) && std::isfinite(golden[i]) && error<=2e-5+2e-5*std::fabs(golden[i]));
        if(error>maximum) maximum=error;
    }
    std::printf("REAL_GGML_PREFILL_PASS key=%s outputs=40960 commands=160 groups=40 value_decodes=480 paired_bitexact=1 max_abs=%.9g hardware=not_executed\n",argv[2],maximum);
    std::free(old_workspace);std::free(workspace);ggml_backend_buffer_free(buffer);ggml_free(ctx);
}
