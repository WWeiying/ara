#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml-quants.h"
#include "repack.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

static void need(bool ok, const char *why) {
    if (!ok) { std::fprintf(stderr,"FLOAT_GAP_GRAPH_FAIL %s\n",why); std::exit(1); }
}
static void env(const char *k,const char *v) { need(setenv(k,v,1)==0,"env"); }
static void run(unsigned mode,const char *path) {
    env("GGML_RISCV_QBS","1"); env("GGML_RISCV_QBS_EMULATE","0");
    env("GGML_RISCV_QBS_ACTIVATION_CONTEXT","1");
    env("GGML_RISCV_QBS_CROSS_OP_CONTEXT","1");
    env("GGML_RISCV_QBS_TRACE","1"); env("GGML_RISCV_QBS_TRACE_CALLS","1");
    env("GGML_RISCV_QBS_TRACE_LIFETIME","1");
    env("GGML_RISCV_QBS_M4_PREPARE","1"); env("GGML_RISCV_QBS_WIDE_M","0");
    env("GGML_QBS_FLOAT_GAP_TEST",mode ? "1":"0");
    std::printf("FLOAT_GAP_GRAPH_MODE mode=%u\n",mode);
    FILE *file=std::fopen(path,"wb"); need(file,"output");
    constexpr int k=256,n=32;
    for (int scenario=0;scenario<3;++scenario) {
        ggml_init_params p{1024*1024,nullptr,true};
        auto *wc=ggml_init(p), *ctx=ggml_init(p); need(wc&&ctx,"contexts");
        auto *w=ggml_new_tensor_2d(wc,GGML_TYPE_Q4_K,k,n);
        auto *wb=ggml_backend_alloc_ctx_tensors_from_buft(wc,ggml_backend_cpu_repack_buffer_type());
        need(wb&&w->extra,"repack");
        std::vector<float> weights(k*n);
        for (int i=0;i<k*n;++i) weights[i]=float((i*17+i/k*3)%127-63)/512;
        std::vector<unsigned char> raw(ggml_row_size(GGML_TYPE_Q4_K,k)*n);
        quantize_row_q4_K_ref(weights.data(),reinterpret_cast<block_q4_K *>(raw.data()),k*n);
        ggml_backend_tensor_set(w,raw.data(),0,raw.size());
        auto *x=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,k,1);
        auto *first=ggml_mul_mat(ctx,w,x);
        auto *graph=ggml_new_graph(ctx);
        ggml_build_forward_expand(graph,first);
        ggml_tensor *gap=nullptr,*fw=nullptr,*fx=nullptr;
        if (scenario<2) {
            fw=ggml_new_tensor_2d(ctx,scenario ? GGML_TYPE_F16:GGML_TYPE_F32,4,4);
            fx=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,4,1);
            gap=ggml_mul_mat(ctx,fw,fx);
        } else {
            gap=ggml_scale_inplace(ctx,x,2.0f);
        }
        ggml_build_forward_expand(graph,gap);
        auto *second=ggml_mul_mat(ctx,w,scenario==2 ? gap:x);
        ggml_build_forward_expand(graph,second);
        auto *backend=ggml_backend_cpu_init(); need(backend,"backend");
        ggml_backend_cpu_set_n_threads(backend,1);
        auto *buffer=ggml_backend_alloc_ctx_tensors(ctx,backend); need(buffer,"buffer");
        if (scenario<2) {
            float identity[16]={}; ggml_fp16_t half[16]={}; float vec[4]={1,2,3,4};
            for(int i=0;i<4;++i) { identity[i*5]=1; half[i*5]=ggml_fp32_to_fp16(1); }
            ggml_backend_tensor_set(fw,scenario ? static_cast<void *>(half):static_cast<void *>(identity),
                                    0,scenario ? sizeof(half):sizeof(identity));
            ggml_backend_tensor_set(fx,vec,0,sizeof(vec));
        }
        const void *address=x->data;
        std::vector<float> inputs(k),a(n),b(n);
        std::vector<float> previous;
        for (int epoch=0;epoch<2;++epoch) {
            for(int i=0;i<k;++i) inputs[i]=float(i==0 ? 127:(i*23+epoch*41)%193-96)/256;
            ggml_backend_tensor_set(x,inputs.data(),0,k*sizeof(float));
            need(x->data==address,"address_changed");
            std::printf("FLOAT_GAP_GRAPH_BEGIN mode=%u scenario=%d epoch=%d\n",mode,scenario,epoch);
            asm volatile("csrwi fcsr,0;csrwi vcsr,0;csrwi vstart,0" ::: "memory");
            need(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"compute");
            uintptr_t fc,vc;
            asm volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
            ggml_backend_tensor_get(first,a.data(),0,n*sizeof(float));
            ggml_backend_tensor_get(second,b.data(),0,n*sizeof(float));
            for(int i=0;i<n;++i) {
                need(std::isfinite(a[i])&&std::isfinite(b[i]),"nonfinite");
                need(b[i]==a[i]*(scenario==2 ? 2.0f:1.0f),"reuse_or_overwrite");
            }
            if(epoch) need(std::memcmp(previous.data(),a.data(),n*sizeof(float))!=0,"stale_epoch");
            previous=a;
            if(scenario<2) {
                float values[4]; ggml_backend_tensor_get(gap,values,0,sizeof(values));
                for(int i=0;i<4;++i) need(values[i]==i+1,"float_gap_result");
            }
            need(std::fwrite(a.data(),sizeof(float),n,file)==n,"write");
            need(std::fwrite(b.data(),sizeof(float),n,file)==n,"write");
            need(std::fwrite(&fc,sizeof(fc),1,file)==1&&std::fwrite(&vc,sizeof(vc),1,file)==1,"csr_write");
            std::printf("FLOAT_GAP_GRAPH_PASS mode=%u scenario=%d epoch=%d\n",mode,scenario,epoch);
        }
        ggml_backend_buffer_free(buffer); ggml_backend_free(backend); ggml_free(ctx);
        ggml_backend_buffer_free(wb); ggml_free(wc);
    }
    need(std::fclose(file)==0,"close");
}
int main() {
    std::setvbuf(stdout,nullptr,_IONBF,0);
    const char *paths[]={"/tmp/float-gap-old","/tmp/float-gap-new"};
    for(unsigned mode=0;mode<2;++mode) {
        pid_t child=fork(); need(child>=0,"fork");
        if(!child) {run(mode,paths[mode]);std::exit(0);}
        int status; need(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"child");
    }
    FILE *a=std::fopen(paths[0],"rb"),*b=std::fopen(paths[1],"rb"); need(a&&b,"paired_files");
    size_t bytes=0;
    for (;;) {int x=std::fgetc(a),y=std::fgetc(b);need(x==y,"paired_output_csr");if(x==EOF)break;++bytes;}
    need(!std::ferror(a)&&!std::ferror(b)&&bytes==1632,"paired_length");
    std::fclose(a);std::fclose(b);
    std::puts("FLOAT_GAP_GRAPH_SUITE_PASS graphs=12 paired_bytes=1632 performance=not_measured");
}
