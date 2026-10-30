#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void option(const char *key,const char *value) { assert(!setenv(key,value,1)); }
static void load(const char *kind,const char *name,void *data,size_t bytes) {
    char path[512];int n=std::snprintf(path,sizeof(path),"/%s/%s",kind,name);
    assert(n>0 && size_t(n)<sizeof(path));auto *f=std::fopen(path,"rb");assert(f);
    assert(std::fread(data,1,bytes,f)==bytes && std::fgetc(f)==EOF);assert(!std::fclose(f));
}

static void profile(bool q4) {
    const char *kind=q4?"q4_0":"q8_0";
    ggml_init_params init{};init.mem_size=4*1024*1024;init.no_alloc=true;
    auto *ctx=ggml_init(init);assert(ctx);
    auto *q=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,128,20,16,1);
    auto *k=ggml_new_tensor_4d(ctx,q4?GGML_TYPE_Q4_0:GGML_TYPE_Q8_0,128,256,8,1);
    auto *v=ggml_new_tensor_4d(ctx,GGML_TYPE_Q8_0,128,256,8,1);
    auto *mask=ggml_new_tensor_4d(ctx,GGML_TYPE_F16,256,32,1,1);
    uint32_t bits=0x3db504f3;float scale;std::memcpy(&scale,&bits,4);
    auto *dst=ggml_flash_attn_ext(ctx,q,k,v,mask,scale,0,0);
    auto *graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,dst);
    assert(ggml_graph_n_nodes(graph)==1);
    auto buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,ggml_backend_cpu_buffer_type());assert(buffer);
    load(kind,"attn_q_input-0.bin",q->data,ggml_nbytes(q));
    load(kind,"attn_k_input-0.bin",k->data,ggml_nbytes(k));
    load(kind,"attn_v_input-0.bin",v->data,ggml_nbytes(v));
    std::memset(mask->data,0,ggml_nbytes(mask));
    load(kind,"attn_mask_input-0.bin",mask->data,10240);
    std::vector<float> golden(40960),baseline(40960);
    load(kind,"kqv_out-0.bin",golden.data(),163840);
    for(unsigned hole=0;hole<2;++hole) {
        if(hole) static_cast<uint16_t *>(mask->data)[19*256+3]=0xfc00;
        for(unsigned enabled=0;enabled<2;++enabled) {
            option("GGML_RISCV_AKV_QUANT_PREFILL",enabled?"1":"0");
            std::printf("PREFILL_GRAPH_BEGIN kind=%s hole=%u enabled=%u\n",kind,hole,enabled);
            std::memset(dst->data,0xa5,ggml_nbytes(dst));
            auto plan=ggml_graph_plan(graph,1,nullptr);std::vector<uint8_t> work(plan.work_size);
            plan.work_data=work.empty()?nullptr:work.data();
            __asm__ volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
            assert(ggml_graph_compute(graph,&plan)==GGML_STATUS_SUCCESS);
            uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc));
            assert(fc<=31 && (fc&8) && vc==5);
            auto *output=static_cast<float *>(dst->data);double maximum=0;
            for(unsigned i=0;i<40960;++i) {
                assert(std::isfinite(output[i]));
                if(!hole) {
                    double e=std::fabs(double(output[i])-golden[i]);
                    assert(e<=2e-5+2e-5*std::fabs(golden[i]));if(e>maximum)maximum=e;
                }
            }
            if(!enabled) std::memcpy(baseline.data(),output,163840);
            else if(hole) assert(!std::memcmp(baseline.data(),output,163840));
            else for(unsigned i=0;i<40960;++i)
                assert(std::fabs(double(output[i])-baseline[i])<=2e-5+2e-5*std::fabs(baseline[i]));
            std::printf("PREFILL_GRAPH_END kind=%s hole=%u enabled=%u outputs=40960 max_abs=%.9g fcsr=%lu vcsr=%lu\n",
                kind,hole,enabled,maximum,(unsigned long)fc,(unsigned long)vc);
        }
    }
    ggml_backend_buffer_free(buffer);ggml_free(ctx);
}

int main() {
    std::setvbuf(stdout,nullptr,_IONBF,0);std::setvbuf(stderr,nullptr,_IONBF,0);
    option("GGML_RISCV_QBS","1");option("GGML_RISCV_QBS_EMULATE","0");
    option("GGML_RISCV_AKV","0");option("GGML_RISCV_AKV_EMULATE","0");
    option("GGML_RISCV_AKV_QUANT_KV","1");option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY","1");
    option("GGML_RISCV_AKV_GROUPED_PV","0");option("GGML_RISCV_AKV_TRACE","1");
    ggml_cpu_init();profile(false);profile(true);
    std::puts("PREFILL_GRAPH_SUITE_PASS profiles=2 calls=8 performance=not_measured");
}
