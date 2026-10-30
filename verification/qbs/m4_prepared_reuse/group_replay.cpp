#include "value_cache.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" bool m4_produce(const float *,void *,int64_t);
extern "C" void quantize_row_q8_K(const float *,void *,int64_t);
extern "C" const float q_input[],v_input[],k_input[],gate_input[],up_input[];
using namespace q8k_m4_experiment;
static constexpr size_t K=1536,Rows=15,Out=7008;
alignas(64) static unsigned char reference[Out+128],actual[Out+128];
static value_cache<> cache;
static unsigned computations=0;
static void need(bool ok,const char *why) {
    if(!ok) {std::printf("M4_GROUP_REPLAY_FAIL reason=%s\n",why);std::exit(1);}
}
static unsigned fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static void state(unsigned flags,unsigned vector_state) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(flags),"r"(vector_state):"memory");
}
static bool prepare(const float *input,void *output) {
    const unsigned before=fc();unsigned start;
    asm volatile("csrr %0,vstart":"=r"(start)::"memory");
    if((before>>5)!=0 || start) return false;
    key identity;identity.k=K;identity.producer_tag=1;
    unsigned raised=0;
    if(!cache.get(identity,input,K*16,output,Out,raised)) {
        asm volatile("fsflags zero":::"memory");
        const bool admitted=m4_produce(input,output,K);
        asm volatile("frflags %0":"=r"(raised)::"memory");
        const unsigned restored=(before&31)|raised;
        asm volatile("fsflags %0"::"r"(restored):"memory");
        if(!admitted) return false;
        ++computations;
        need(cache.put(identity,input,K*16,output,Out,raised),"store");
    }
    const unsigned restored=(before&31)|raised;
    asm volatile("fsflags %0"::"r"(restored):"memory");
    return true;
}
int main() {
    const float *inputs[]={q_input,v_input,k_input,gate_input,up_input,q_input};
    need(&q_input[0]!=&v_input[0] && &q_input[0]!=&k_input[0] &&
         &gate_input[0]!=&up_input[0],"distinct_storage");
    need(std::memcmp(q_input,v_input,Rows*K*4)==0 &&
         std::memcmp(q_input,k_input,Rows*K*4)==0 &&
         std::memcmp(gate_input,up_input,Rows*K*4)==0,"capture_relationship");
    unsigned checks=0,tails=0;
    for(unsigned pass=0;pass<6;++pass) {
        for(unsigned group=0;group<Rows/4;++group) {
            const float *input=inputs[pass]+group*4*K;
            std::memset(reference,0xa5,sizeof(reference));std::memset(actual,0xa5,sizeof(actual));
            state(pass*3,pass);
            need(m4_produce(input,reference+64,K),"baseline_domain");
            const unsigned expected_fc=fc(),expected_vc=vc();
            state(pass*3,pass);need(prepare(input,actual+64),"cache_domain");
            need(fc()==expected_fc && vc()==expected_vc,"m4_state");
            need(std::memcmp(reference,actual,sizeof(reference))==0,"m4_bytes_or_guards");++checks;
        }
        for(unsigned row=(Rows/4)*4;row<Rows;++row) {
            const float *input=inputs[pass]+row*K;
            std::memset(reference,0xa5,sizeof(reference));std::memset(actual,0xa5,sizeof(actual));
            state(pass*3,pass);quantize_row_q8_K(input,reference+64,K);
            const unsigned expected_fc=fc(),expected_vc=vc();
            state(pass*3,pass);quantize_row_q8_K(input,actual+64,K);
            need(fc()==expected_fc && vc()==expected_vc,"tail_state");
            need(std::memcmp(reference,actual,sizeof(reference))==0,"tail_bytes_or_guards");
            ++tails;++checks;
        }
    }
    const auto &s=cache.statistics();
    need(computations==6 && s.misses==6 && s.hits==12 && s.conflicts==0 &&
         s.evictions==0 && cache.size()==6,"accounting");
    std::printf("M4_GROUP_REPLAY_PASS checks=%u computations=%u hits=%llu misses=%llu tails=%u\n",
                checks,computations,(unsigned long long)s.hits,(unsigned long long)s.misses,tails);
    return checks==36 && tails==18 ? 0:2;
}
