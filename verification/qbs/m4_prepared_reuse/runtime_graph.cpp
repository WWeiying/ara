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

extern "C" const float real_activation[];
static void need(bool ok,const char *why) {
    if(!ok) {std::fprintf(stderr,"M4_RUNTIME_GRAPH_FAIL reason=%s\n",why);std::exit(1);}
}
static void side_write(ggml_tensor *dst,const ggml_tensor *a,int ith,int nth,void *opaque) {
    need(ith==0 && nth==1,"custom_threads");
    auto *x=static_cast<ggml_tensor *>(opaque);auto *values=static_cast<float *>(x->data);
    for(int64_t i=0;i<ggml_nelements(x);++i) values[i]*=2.0f;
    std::memcpy(dst->data,a->data,ggml_nbytes(a));
}
static void run(unsigned mode,const char *path) {
    auto env=[](const char *k,const char *v) {need(setenv(k,v,1)==0,"environment");};
    env("GGML_RISCV_QBS","1");env("GGML_RISCV_QBS_EMULATE","0");
    env("GGML_RISCV_QBS_M4_PREPARE","1");env("GGML_RISCV_QBS_WIDE_M","0");
    env("GGML_RISCV_QBS_M4_CACHE",mode ? "1":"0");
    env("GGML_RISCV_QBS_TRACE_M4_PREPARE","1");
    std::printf("M4_RUNTIME_GRAPH_MODE mode=%u\n",mode);
    std::fflush(stdout);
    FILE *file=std::fopen(path,"wb");need(file,"output");
    constexpr int k=1536,n=32,m=15;
    for(unsigned scenario=0;scenario<6;++scenario) {
        ggml_init_params p{4*1024*1024,nullptr,true};
        auto *wc=ggml_init(p),*ctx=ggml_init(p);need(wc && ctx,"contexts");
        auto *w=ggml_new_tensor_2d(wc,GGML_TYPE_Q4_K,k,n);
        auto *wb=ggml_backend_alloc_ctx_tensors_from_buft(wc,ggml_backend_cpu_repack_buffer_type());
        need(wb && w->extra,"repacked_weights");
        std::vector<float> weights(k*n);
        for(int i=0;i<k*n;++i) weights[i]=float((i*17+i/k*3)%127-63)/512;
        std::vector<unsigned char> raw(ggml_row_size(GGML_TYPE_Q4_K,k)*n);
        quantize_row_q4_K_ref(weights.data(),reinterpret_cast<block_q4_K *>(raw.data()),k*n);
        ggml_backend_tensor_set(w,raw.data(),0,raw.size());
        auto *x=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,k,m);
        auto *first=ggml_mul_mat(ctx,w,x);auto *graph=ggml_new_graph(ctx);
        ggml_build_forward_expand(graph,first);
        ggml_tensor *gap=nullptr,*fw=nullptr,*fx=nullptr;
        if(scenario==1) {
            fw=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,4,4);
            fx=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,4,1);
            gap=ggml_mul_mat(ctx,fw,fx);
        } else if(scenario==2) gap=ggml_scale_inplace(ctx,x,2.0f);
        else if(scenario==3) {
            fx=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,4);
            gap=ggml_map_custom1(ctx,fx,side_write,1,x);
        }
        if(gap) ggml_build_forward_expand(graph,gap);
        auto *second=ggml_mul_mat(ctx,w,scenario==2 ? gap:x);
        ggml_build_forward_expand(graph,second);
        auto *backend=ggml_backend_cpu_init();need(backend,"backend");
        ggml_backend_cpu_set_n_threads(backend,scenario==4 ? 2:1);
        auto *buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);need(buffer,"buffer");
        if(scenario==1) {
            float identity[16]={},vec[4]={1,2,3,4};for(int i=0;i<4;++i) identity[i*5]=1;
            ggml_backend_tensor_set(fw,identity,0,sizeof(identity));ggml_backend_tensor_set(fx,vec,0,sizeof(vec));
        } else if(scenario==3) {float vec[4]={1,2,3,4};ggml_backend_tensor_set(fx,vec,0,sizeof(vec));}
        std::vector<float> inputs(real_activation,real_activation+k*m),a(n*m),b(n*m);
        const void *address=x->data;
        for(unsigned epoch=0;epoch<2;++epoch) {
            if(epoch) for(auto &value:inputs) value*=0.5f;
            ggml_backend_tensor_set(x,inputs.data(),0,k*m*sizeof(float));need(x->data==address,"address_changed");
            std::printf("M4_RUNTIME_GRAPH_BEGIN mode=%u scenario=%u epoch=%u\n",mode,scenario,epoch);
            std::fflush(stdout);
            const uintptr_t initial=(scenario==5 ? 3u<<5:0u)|17u;
            asm volatile("csrw fcsr,%0;csrwi vcsr,5;csrwi vstart,0"::"r"(initial):"memory");
            need(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"compute");
            uintptr_t fc,vc;asm volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
            ggml_backend_tensor_get(first,a.data(),0,a.size()*sizeof(float));
            ggml_backend_tensor_get(second,b.data(),0,b.size()*sizeof(float));
            for(size_t i=0;i<a.size();++i) need(std::isfinite(a[i]) && std::isfinite(b[i]),"nonfinite");
            need(std::fwrite(a.data(),sizeof(float),a.size(),file)==a.size(),"write_first");
            need(std::fwrite(b.data(),sizeof(float),b.size(),file)==b.size(),"write_second");
            const uint64_t states[2]={uint64_t(fc),uint64_t(vc)};
            need(std::fwrite(states,sizeof(uint64_t),2,file)==2,"write_state");
            std::printf("M4_RUNTIME_GRAPH_PASS mode=%u scenario=%u epoch=%u fc=%llu vc=%llu\n",
                        mode,scenario,epoch,(unsigned long long)fc,(unsigned long long)vc);
            std::fflush(stdout);
        }
        ggml_backend_buffer_free(buffer);ggml_backend_free(backend);ggml_backend_buffer_free(wb);
        ggml_free(ctx);ggml_free(wc);
    }
    need(std::fclose(file)==0,"close");
}
int main() {
    for(unsigned mode=0;mode<2;++mode) {
        pid_t pid=fork();need(pid>=0,"fork");
        if(pid==0) {run(mode,mode ? "/tmp/cache.bin":"/tmp/baseline.bin");std::exit(0);}
        int status;need(waitpid(pid,&status,0)==pid && WIFEXITED(status) && WEXITSTATUS(status)==0,"child");
    }
    FILE *a=std::fopen("/tmp/baseline.bin","rb"),*b=std::fopen("/tmp/cache.bin","rb");need(a && b,"compare_open");
    unsigned bytes=0;int x,y;
    do {x=std::fgetc(a);y=std::fgetc(b);need(x==y,"paired_bytes_or_state");bytes+=x!=EOF;} while(x!=EOF);
    need(std::fclose(a)==0 && std::fclose(b)==0 && bytes==46272,"compare_complete");
    std::printf("M4_RUNTIME_GRAPH_SUITE_PASS graphs=24 paired_bytes=%u performance=not_measured\n",bytes);
}
