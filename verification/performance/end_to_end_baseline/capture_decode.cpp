#include "llama.h"
#include "ggml-backend.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void need(bool ok,const char *why) {
    if (!ok) {std::fprintf(stderr,"DECODE_CAPTURE_FAIL reason=%s\n",why);std::exit(1);}
}
static void env(const char *key,const char *value) {need(!setenv(key,value,1),"environment");}
#include "capture_environment.h"
static bool decoding=false;
static unsigned captured=0;
static const char *names[]={"attn_norm-0","ffn_norm-0","ffn_swiglu-0","result_norm"};
static const unsigned widths[]={2048,2048,6144,2048};

static bool capture(ggml_tensor *tensor,bool ask,void *) {
    if (!decoding) return false;
    unsigned part=0;while(part<4 && std::strcmp(tensor->name,names[part])) ++part;
    if(part==4) return false;
    if(ask) return true;
    need(part==captured,"boundary_order");const unsigned k=widths[part];
    need(tensor->type==GGML_TYPE_F32 && tensor->ne[0]==k && tensor->ne[1]==1 && tensor->ne[2]==1 &&
         tensor->ne[3]==1 && ggml_is_contiguous(tensor) && tensor->nb[0]==4 && tensor->nb[1]==k*4,"shape/layout");
    std::vector<float> data(k);ggml_backend_tensor_get(tensor,data.data(),0,k*4);
    for(float value:data) need(std::isfinite(value),"nonfinite");
    std::printf("DECODE_CAPTURE_SHAPE source=%s k=%u rows=1 type=f32\n",names[part],k);
    for(unsigned offset=0;offset<k;offset+=16) {
        std::printf("DECODE_CAPTURE_DATA source=%s offset=%u bits=",names[part],offset);
        for(unsigned i=0;i<16;++i) {uint32_t bits;std::memcpy(&bits,&data[offset+i],4);std::printf("%08x",bits);}
        std::putchar('\n');
    }
    if(++captured==4) {
        std::puts("DECODE_CAPTURE_DONE sources=4 bytes=49152 stop=before_decode_vocabulary performance=not_measured");
        std::exit(0);
    }
    return true;
}

int main() {
    std::setvbuf(stdout,nullptr,_IONBF,0);std::setvbuf(stderr,nullptr,_IONBF,0);configure_capture();
    // Trace choices change only between completed graph calls, never mid-command.
    env("GGML_RISCV_QBS_TRACE","0");env("GGML_RISCV_QBS_TRACE_LIFETIME","0");
    llama_backend_init();auto mp=llama_model_default_params();mp.n_gpu_layers=0;
    auto *model=llama_model_load_from_file("/model/models/Qwen3-1.7B-Q4_K_M.gguf",mp);
    need(model && llama_model_n_layer(model)==28,"model");auto *vocab=llama_model_get_vocab(model);
    need(llama_vocab_n_tokens(vocab)==151936,"vocabulary");
    const char prompt[]="A vector processor executes the same operation on many data elements. Explain how quantized matrix multiplication and attention use this parallelism, and discuss the role of memory bandwidth when generating text with a language model.";
    std::vector<llama_token> tokens(256);
    const int n=llama_tokenize(vocab,prompt,sizeof(prompt)-1,tokens.data(),tokens.size(),true,true);
    need(n==40,"prompt");tokens.resize(n);
    std::printf("DECODE_CAPTURE_TOKENS count=40 ids=");
    for(int i=0;i<n;++i) std::printf("%s%d",i?",":"",tokens[i]);
    std::putchar('\n');
    auto cp=llama_context_default_params();cp.n_ctx=128;cp.n_batch=cp.n_ubatch=64;
    cp.n_threads=cp.n_threads_batch=1;cp.type_k=cp.type_v=GGML_TYPE_Q8_0;
    cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;cp.cb_eval=capture;
    auto *ctx=llama_init_from_model(model,cp);need(ctx,"context");
    asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
    need(llama_decode(ctx,llama_batch_get_one(tokens.data(),n))==0,"prefill");
    const float *logits=llama_get_logits_ith(ctx,-1);need(logits,"logits");
    for(unsigned i=0;i<151936;++i) need(std::isfinite(logits[i]),"finite_prefill_logits");
    llama_token token=std::max_element(logits,logits+151936)-logits;
    need(token==22406,"accepted_prefill_token");
    std::printf("DECODE_CAPTURE_BEGIN prompt=40 token=%d position=40 kv=q8_0 qbs=1\n",token);
    env("GGML_RISCV_QBS_TRACE","1");env("GGML_RISCV_QBS_TRACE_LIFETIME","1");decoding=true;
    asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
    (void)llama_decode(ctx,llama_batch_get_one(&token,1));
    need(false,"missing_decode_boundary");
}
