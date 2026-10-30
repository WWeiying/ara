#include "value_cache.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" bool m4_produce(const float *,void *,int64_t);
extern "C" const float real_input[];
extern "C" const unsigned char golden_packed[];
using namespace q8k_m4_experiment;
static constexpr size_t K=1536,In=K*16,Out=7008;
alignas(64) static float input[4*K];
alignas(64) static unsigned char reference[Out+128],actual[Out+128];
static value_cache<> cache;
static unsigned computations=0,checks=0;
static void need(bool ok,const char *why) {
    if(!ok) {std::printf("M4_CACHE_REPLAY_FAIL reason=%s\n",why);std::exit(1);}
}
static unsigned fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static void state(unsigned f,unsigned v) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(f),"r"(v):"memory");
}
// Experimental call site: production quantizer and runtime remain unchanged.
__attribute__((noinline)) static bool prepare(void *output) {
    const unsigned before=fc();unsigned start;
    asm volatile("csrr %0,vstart":"=r"(start)::"memory");
    if((before>>5)!=0 || start!=0) return false;
    key identity;identity.k=K;identity.producer_tag=1;
    unsigned raised=0;
    if(!cache.get(identity,input,In,output,Out,raised)) {
        asm volatile("fsflags zero":::"memory");
        const bool admitted=m4_produce(input,output,K);
        asm volatile("frflags %0":"=r"(raised)::"memory");
        const unsigned restored=(before&31)|raised;
        asm volatile("fsflags %0"::"r"(restored):"memory");
        if(!admitted) return false;
        ++computations;
        need(cache.put(identity,input,In,output,Out,raised),"store_failed");
    }
    const unsigned restored=(before&31)|raised;
    asm volatile("fsflags %0"::"r"(restored):"memory");
    return true;
}
static void compare(unsigned flags,unsigned vector_state,bool golden) {
    std::memset(reference,0xa5,sizeof(reference));
    std::memset(actual,0xa5,sizeof(actual));
    state(flags,vector_state);
    need(m4_produce(input,reference+64,K),"baseline_domain");
    const unsigned expected_fc=fc(),expected_vc=vc();
    state(flags,vector_state);
    need(prepare(actual+64),"cache_domain");
    need(fc()==expected_fc && vc()==expected_vc,"state_mismatch");
    need(std::memcmp(reference,actual,sizeof(reference))==0,"output_or_guard_mismatch");
    if(golden) need(std::memcmp(actual+64,golden_packed,Out)==0,"golden_mismatch");
    ++checks;
}
int main() {
    std::memcpy(input,real_input,In);
    compare(17,5,true); // Cold miss must include real production and snapshot ownership.
    need(computations==1 && cache.statistics().misses==1,"cold_accounting");
    for(unsigned f=0;f<32;++f)
        for(unsigned v=0;v<8;++v) compare(f,v,true);
    need(computations==1 && cache.statistics().hits==256,"warm_accounting");
    for(size_t p:{size_t(0),2*K,4*K-1}) {
        input[p]=input[p]*0.5f+0.125f;
        const auto misses=cache.statistics().misses,hits=cache.statistics().hits;
        compare(8,3,false);compare(16,7,false);
        need(cache.statistics().misses==misses+1 && cache.statistics().hits==hits+1,"mutation_accounting");
    }
    std::memcpy(input,real_input,In);compare(0,0,true);
    need(computations==4,"original_snapshot_lost");
    for(unsigned rounding=1;rounding<=4;++rounding) {
        std::memset(actual,0xa5,sizeof(actual));state((rounding<<5)|8,3);
        need(!prepare(actual+64),"non_rne_admitted");
        need(fc()==((rounding<<5)|8) && vc()==3,"rejected_state");
        for(auto b:actual) need(b==0xa5,"rejected_write");
        ++checks;
    }
    state(8,3);asm volatile("csrwi vstart,1":::"memory");
    const bool accepted=prepare(actual+64);unsigned start;
    asm volatile("csrr %0,vstart;csrwi vstart,0":"=r"(start)::"memory");
    need(!accepted && start==1 && fc()==8 && vc()==3,"restart_rejection");++checks;
    need(cache.statistics().conflicts==0 && cache.statistics().hits==260,"final_accounting");
    std::printf("M4_CACHE_REPLAY_PASS checks=%u computations=%u hits=%llu misses=%llu\n",
        checks,computations,(unsigned long long)cache.statistics().hits,
        (unsigned long long)cache.statistics().misses);
    return checks==269 ? 0:2;
}
