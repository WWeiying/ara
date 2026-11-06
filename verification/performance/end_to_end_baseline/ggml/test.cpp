#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

static std::vector<unsigned char> load(const std::string &path,size_t size) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    assert(f && f.tellg()==static_cast<std::streamoff>(size));f.seekg(0);
    std::vector<unsigned char> b(size);f.read(reinterpret_cast<char*>(b.data()),size);
    assert(f.good());return b;
}
static uintptr_t compute(ggml_context *ctx,ggml_cgraph *graph,int threads) {
    __asm__ volatile("csrwi fcsr,8;csrwi vcsr,5":::"memory");
    assert(ggml_graph_compute_with_ctx(ctx,graph,threads)==GGML_STATUS_SUCCESS);
    uintptr_t flags,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(flags),"=r"(vc));
    assert(vc==5);return flags;
}
static void mode(bool output,bool reg,bool native=true) {
    setenv("GGML_RISCV_AKV_OUTPUT_TILE",output?"1":"0",1);
    setenv("GGML_RISCV_AKV_REGISTER_PV",reg?"1":"0",1);
    setenv("GGML_RISCV_AKV_QUANT_KV",native?"1":"0",1);
}
static void profile(bool q3,bool q4) {
    const std::string name=std::string(q3?"qwen3":"qwen25")+(q4?"_q4":"_q8");
    const std::string dir="/"+name;
    const unsigned heads=q3?16:12,kv=q3?8:2,queries=q3?20:1;
    ggml_init_params init{};init.mem_size=4*1024*1024;init.no_alloc=true;
    auto *ctx=ggml_init(init);assert(ctx);
    auto *qfull=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,128,queries,heads,1);
    auto *mfull=ggml_new_tensor_4d(ctx,GGML_TYPE_F16,256,queries,1,1);
    auto *q=q3?ggml_view_4d(ctx,qfull,128,1,heads,1,qfull->nb[1],qfull->nb[2],qfull->nb[3],19*512):qfull;
    auto *mask=q3?ggml_view_4d(ctx,mfull,256,1,1,1,mfull->nb[1],mfull->nb[2],mfull->nb[3],19*512):mfull;
    auto *k=ggml_new_tensor_4d(ctx,q4?GGML_TYPE_Q4_0:GGML_TYPE_Q8_0,128,256,kv,1);
    auto *v=ggml_new_tensor_4d(ctx,GGML_TYPE_Q8_0,128,256,kv,1);
    uint32_t bits=0x3db504f3;float scale;std::memcpy(&scale,&bits,4);
    auto *dst=ggml_flash_attn_ext(ctx,q,k,v,mask,scale,0,0);
    auto *graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,dst);
    auto buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,ggml_backend_cpu_buffer_type());assert(buffer);
    ggml_tensor *inputs[]={qfull,k,v,mfull};
    const char *files[]={"attn_q_input-0.bin","attn_k_input-0.bin","attn_v_input-0.bin","attn_mask_input-0.bin"};
    std::vector<unsigned char> originals[4];
    for(unsigned i=0;i<4;++i) {
        originals[i]=load(dir+"/"+files[i],ggml_nbytes(inputs[i]));
        ggml_backend_tensor_set(inputs[i],originals[i].data(),0,originals[i].size());
    }
    const auto gold=load(dir+"/kqv_out-0.bin",heads*128*queries*4);
    const size_t bytes=heads*128*4;
    std::vector<unsigned char> baseline(bytes),ordinary(bytes);
    mode(false,false,false);compute(ctx,graph,1);std::memcpy(ordinary.data(),dst->data,bytes);
    uintptr_t baseline_flags=0;
    for(unsigned trial=0;trial<3;++trial) {
        const bool candidate=trial!=0;mode(candidate,!candidate);
        std::memset(dst->data,0xa5,bytes);
        std::printf("OUTPUT_GRAPH_BEGIN name=%s candidate=%u repeat=%u\n",name.c_str(),candidate,trial);std::fflush(stdout);
        const uintptr_t flags=compute(ctx,graph,1);
        if(!trial) { std::memcpy(baseline.data(),dst->data,bytes);baseline_flags=flags; }
        else assert(flags==baseline_flags && !std::memcmp(baseline.data(),dst->data,bytes));
        const auto *y=static_cast<const float*>(dst->data);float max_error=0;
        for(unsigned i=0;i<heads*128;++i) {
            float expected;std::memcpy(&expected,gold.data()+(q3?19*bytes:0)+i*4,4);
            assert(std::isfinite(y[i]) && std::isfinite(expected));
            const float e=std::fabs(y[i]-expected);
            assert(e<=2e-5f+2e-5f*std::fabs(expected));max_error=std::fmax(max_error,e);
        }
        std::printf("OUTPUT_GRAPH_END name=%s candidate=%u repeat=%u flags=%lu max_abs=%.9g\n",
                    name.c_str(),candidate,trial,static_cast<unsigned long>(flags),static_cast<double>(max_error));
    }
    // Conflicting selections and non-normal memory must use the ordinary graph.
    for(unsigned reject=0;reject<2;++reject) {
        mode(true,reject==0);setenv("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY",reject?"0":"1",1);
        std::memset(dst->data,0xa5,bytes);compute(ctx,graph,1);
        assert(!std::memcmp(ordinary.data(),dst->data,bytes));
    }
    setenv("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY","1",1);
    for(unsigned i=0;i<4;++i) assert(!std::memcmp(inputs[i]->data,originals[i].data(),originals[i].size()));
    std::printf("OUTPUT_GRAPH_PROFILE_PASS name=%s heads=%u kv=%u visible=%u outputs=%u native_calls=3 rejected=2 exact=1 inputs_unchanged=1\n",
                name.c_str(),heads,kv,q3?20:128,heads*128);
    ggml_backend_buffer_free(buffer);ggml_free(ctx);
}
int main() {
    setenv("GGML_RISCV_QBS","1",1);setenv("GGML_RISCV_QBS_EMULATE","0",1);
    setenv("GGML_RISCV_AKV","0",1);setenv("GGML_RISCV_AKV_EMULATE","0",1);
    setenv("GGML_RISCV_AKV_GROUPED_PV","0",1);setenv("GGML_RISCV_AKV_TRACE","1",1);
    setenv("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY","1",1);ggml_cpu_init();
    for(bool q3:{false,true})for(bool q4:{false,true})profile(q3,q4);
    std::puts("OUTPUT_GRAPH_SUITE_PASS profiles=4 native_calls=12 fallback_calls=8");
}
