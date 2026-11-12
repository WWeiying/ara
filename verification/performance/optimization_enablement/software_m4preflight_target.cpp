#include "q8_K-prepared-reuse.h"
#include <new>

#define NI __attribute__((no_instrument_function))
extern "C" const unsigned test_case;
extern "C" const float real_input[];
extern "C" void frozen_generic(const float *, void *, int64_t);
extern "C" void test_text(const char *);
extern "C" void test_number(uint64_t);
extern "C" void test_exit(unsigned) __attribute__((noreturn));
static constexpr size_t K=1536, In=4*K*sizeof(float), Bytes=7008;
alignas(64) static float input[4*K], saved[4*K];
alignas(64) static unsigned char expected[Bytes+128], actual[Bytes+128];
alignas(64) static unsigned char heap[512*1024];
static size_t used;
static unsigned generic_calls, candidate_calls, checks;
static unsigned abort_candidate, abort_generic;
static uint64_t abort_queries;
static void *watched_output;
static size_t watched_bytes;
static ggml_riscv_q8_K_prepared::state *watched_cache;
static ggml_tensor x{}, w{}, ops[2]{};
static ggml_tensor *nodes[2]={&ops[0],&ops[1]};
static ggml_cgraph graph{};
static unsigned graph_count=2;
static float results[2][256];

static unsigned NI fc() {unsigned v;asm volatile("frcsr %0":"=r"(v)::"memory");return v;}
static unsigned NI vc() {unsigned v;asm volatile("csrr %0,vcsr":"=r"(v)::"memory");return v;}
static unsigned NI vs() {unsigned v;asm volatile("csrr %0,vstart":"=r"(v)::"memory");return v;}
static void NI state(unsigned f,unsigned v) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(f),"r"(v):"memory");
}
static void NI need(bool ok,const char *why) {
    ++checks;
    if(!ok) {test_text("M4_PREFLIGHT_FAIL reason=");test_text(why);test_text("\n");test_exit(1);}
}
static bool NI untouched() {
    const auto *p=static_cast<const unsigned char *>(watched_output);
    for(size_t i=0;i<watched_bytes;++i) if(p[i]!=0xa5) return false;
    return true;
}
extern "C" void NI __cyg_profile_func_enter(void *fn,void *) {
#ifdef GGML_USE_RISCV_QBS_M4_PREFLIGHT
    if(fn==reinterpret_cast<void *>(&qbs_experimental_m4_preflight::quantize)) ++candidate_calls;
#else
    (void)fn;
#endif
}
extern "C" void NI __cyg_profile_func_exit(void *,void *) {}

// Only environment and graph/capability metadata are supplied by the harness.
extern "C" char *NI getenv(const char *name) noexcept {
    if(std::strcmp(name,"GGML_RISCV_ACCEL_AUTO")==0)
        return test_case==6 ? const_cast<char *>("0") : nullptr;
    const char *flags[]={"GGML_RISCV_QBS_M4_PREFLIGHT","GGML_RISCV_QBS_M4_PREPARE",
        "GGML_RISCV_QBS_M4_CACHE","GGML_RISCV_QBS_M4_PACKED","GGML_RISCV_QBS_M4_PARALLEL_SUMS"};
    for(unsigned i=0;i<5;++i) if(std::strcmp(name,flags[i])==0) {
        if(test_case==i+1) return const_cast<char *>("0");
        if(test_case==6 && i) return const_cast<char *>("1");
    }
    return nullptr;
}
extern "C" int NI ggml_graph_n_nodes(ggml_cgraph *) {return graph_count;}
extern "C" ggml_tensor *NI ggml_graph_node(ggml_cgraph *,int i) {return nodes[i];}
extern "C" bool NI ggml_is_contiguous(const ggml_tensor *t) {
    size_t stride=sizeof(float);
    for(unsigned i=0;i<4;++i) {if(t->nb[i]!=stride)return false;stride*=t->ne[i];}
    return true;
}
extern "C" size_t NI ggml_nbytes(const ggml_tensor *t) {
    return size_t(t->ne[0]*t->ne[1]*t->ne[2]*t->ne[3])*sizeof(float);
}
bool NI ggml_riscv_qbs_supports_tensor(ggml_type type,int64_t k,int64_t n) {
    return type==GGML_TYPE_Q4_K && k>0 && k%256==0 && n==64;
}
bool NI ggml_riscv_qbs_plan_activations(ggml_type,int64_t,int64_t,int64_t,
        ggml_riscv_qbs_activation_plan *plan) {*plan={};return true;}

namespace std {const nothrow_t nothrow;}
void *NI operator new[](size_t n,const std::nothrow_t &) noexcept {
    n=(n+63)&~size_t(63);
    if(n>sizeof(heap)-used) return nullptr;
    void *p=heap+used;used+=n;return p;
}
void NI operator delete[](void *) noexcept {}
void NI operator delete[](void *,size_t) noexcept {}

extern "C" void NI ggml_quantize_mat_q8_K_4x1_ara_generic(const float *a,void *b,int64_t k) {
    need(b==watched_output && untouched(),"generic_before_any_output_write");
    ++generic_calls;frozen_generic(a,b,k);
}
extern "C" void NI ggml_abort(const char *,int,const char *,...) {
    if(test_case==11) {
        // Do not clear VSTART, invoke libc, compare vector bytes or return to caller.
        if(vs()!=1 || fc()!=17 || vc()!=5 || candidate_calls!=abort_candidate ||
           generic_calls!=abort_generic || !watched_cache ||
           watched_cache->bytes.statistics().queries!=abort_queries || !untouched()) test_exit(2);
        test_text("M4_PREFLIGHT_VSTART_ABORT_PASS candidate_delta=0 generic_delta=0 cache_queries_delta=0 vstart=1\n");
        test_exit(0);
    }
    test_text("M4_PREFLIGHT_UNEXPECTED_ABORT\n");test_exit(3);
}

__attribute__((noinline)) static bool prepare(ggml_riscv_q8_K_prepared::state &cache,
        ggml_riscv_m4_reuse::policy policy,int64_t k) {
    return cache.prepare(policy,input,actual+64,k,0,false);
}
static void shape(ggml_tensor &t,int64_t n,int64_t m,void *data) {
    t.type=GGML_TYPE_F32;t.data=data;
    t.ne[0]=n;t.ne[1]=m;t.ne[2]=t.ne[3]=1;t.nb[0]=4;
    for(unsigned i=1;i<4;++i)t.nb[i]=t.nb[i-1]*t.ne[i-1];
}
int main() {
    const unsigned k=test_case==7 ? 512:1536;
    const size_t bytes=k/256*sizeof(block_q8_Kx4);
    std::memcpy(input,real_input,In);
    if(test_case>=12 && test_case<=15) {
        const uint32_t invalid[]={0x00000001u,0x7f800000u,0x7fc01234u,0x7f801234u};
        std::memcpy(input+4*k-1,invalid+test_case-12,4);
    }
    std::memcpy(saved,input,In);
    shape(x,k,4,input);shape(w,k,64,nullptr);w.type=GGML_TYPE_Q4_K;w.extra=&w;
    for(unsigned i=0;i<2;++i) {
        shape(ops[i],64,4,results[i]);ops[i].op=GGML_OP_MUL_MAT;
        ops[i].src[0]=&w;ops[i].src[1]=&x;
    }
    graph_count=test_case==9 ? 1:2;
    ggml_compute_params params{};params.nth=test_case==8 ? 2:1;
    params.graph_epoch=1;params.cgraph=&graph;params.node_index=0;
    ggml_riscv_q8_K_prepared::state cache;
    const auto policy=cache.begin(&params,&ops[0]);
    const bool selected=ggml_riscv_q8_K_preflight::enabled(k,cache.single_worker,policy.lookup);
    const bool wanted=test_case==0 || test_case==10 || test_case==11 || (test_case>=12 && test_case<=15);
    need(selected==wanted,"preflight_selection");
    need(ggml_riscv_q8_K_preflight::producer_tag(selected)==
        (selected ? 4u:ggml_riscv_q8_K_m4_packed::producer_tag()),"tag_before_lookup");

    std::memset(expected,0xa5,sizeof(expected));std::memset(actual,0xa5,sizeof(actual));
    watched_output=expected+64;watched_bytes=bytes;state(0,5);
    ggml_riscv_q8_K_m4_packed::selected_quantize(input,expected+64,k);
    const unsigned raised=fc()&31;
    generic_calls=candidate_calls=0;watched_output=actual+64;
    if(test_case==10) {
        state(49,5);need(!prepare(cache,policy,k),"non_rne_rejection");
        need(fc()==49 && vc()==5 && vs()==0 && untouched(),"non_rne_state_output");
        need(candidate_calls==0 && generic_calls==0,"non_rne_no_producer");
    } else if(test_case==8 || test_case==9) {
        state(17,5);need(!prepare(cache,policy,k),"no_lookup_rejection");
        need(untouched() && candidate_calls==0 && generic_calls==0,"no_lookup_no_producer");
    } else {
        state(17,5);need(prepare(cache,policy,k),"completed_prepare_returns_true");
        need(fc()==(17|raised) && vc()==5 && vs()==0,"cold_csr");
        need(std::memcmp(expected,actual,sizeof(actual))==0,"cold_bytes_guards");
        need(candidate_calls==unsigned(selected),"candidate_actual_entries");
        if(test_case>=12 && test_case<=15) {
            need(generic_calls==1 && cache.computations==1 && cache.generic_computations==1,
                 "late_bad_domain_single_generic");
            need(cache.bytes.size()==0,"generic_not_cached");
        } else {
            need(generic_calls==0 && cache.bytes.statistics().stores==1,"cold_vector_store");
            if(test_case==11) {
                std::memset(actual,0xa5,sizeof(actual));watched_cache=&cache;
                abort_candidate=candidate_calls;abort_generic=generic_calls;
                abort_queries=cache.bytes.statistics().queries;state(17,5);
                asm volatile("csrwi vstart,1":::"memory");
                (void)prepare(cache,policy,k);test_exit(4);
            }
            for(unsigned f=0;f<(test_case==0 ? 32u:1u);++f)for(unsigned v=0;v<(test_case==0 ? 8u:1u);++v) {
                std::memset(actual,0xa5,sizeof(actual));state(f,v);
                need(prepare(cache,policy,k),"warm_prepare");
                need(fc()==(f|raised) && vc()==v && vs()==0,"warm_csr");
                need(std::memcmp(expected,actual,sizeof(actual))==0,"warm_bytes_guards");
            }
            need(candidate_calls==unsigned(selected) && generic_calls==0 && cache.computations==1,
                 "warm_no_producer");
            ggml_riscv_q8_K_cache::key other;other.k=k;other.producer_tag=selected ? 3:4;
            unsigned flags=0;
            need(!cache.bytes.get(other,input,4*k*sizeof(float),actual+64,bytes,flags),"cross_producer_cache_miss");
        }
    }
    state(0,0);need(std::memcmp(saved,input,In)==0,"input_unchanged");
    test_text("M4_PREFLIGHT_TARGET_PASS case=");test_number(test_case);
    test_text(" checks=");test_number(checks);test_text(" candidate_entries=");test_number(candidate_calls);
    test_text(" generic_entries=");test_number(generic_calls);test_text("\n");
    return 0;
}

extern "C" int NI strcmp(const char *a,const char *b) {
    while(*a && *a==*b){++a;++b;}
    return int(static_cast<unsigned char>(*a))-int(static_cast<unsigned char>(*b));
}
