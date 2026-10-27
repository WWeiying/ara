#include "value_cache.hpp"
#include "printf.h"
#include <cstdlib>
#include <cstring>

extern "C" bool m4_produce(const float *,void *,int64_t);
extern "C" const float projection_input[];
extern "C" const unsigned char projection_golden[];
using namespace q8k_m4_experiment;
static constexpr size_t K=1536,In=K*16,Out=7008;
alignas(64) static unsigned char output[3][Out+128];
// The standalone ELF has no OS allocator. Newlib malloc uses this bounded heap;
// its cold allocation is inside the candidate measurement, unlike static slabs.
alignas(64) static unsigned char heap[128*1024];
extern "C" void *_sbrk(ptrdiff_t increment) {
    static size_t used=0;
    if(increment<0 || size_t(increment)>sizeof(heap)-used) return reinterpret_cast<void *>(-1);
    void *p=heap+used;used+=size_t(increment);return p;
}
static uint64_t cycle() {
    uint64_t x;asm volatile("fence rw,rw;rdcycle %0":"=r"(x)::"memory");return x;
}
static unsigned fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
__attribute__((noinline)) static bool prepare(value_cache<> &cache,void *destination) {
    const unsigned before=fc();unsigned start;
    asm volatile("csrr %0,vstart":"=r"(start)::"memory");
    if((before>>5)!=0 || start) return false;
    key identity;identity.k=K;identity.producer_tag=1;
    unsigned raised=0;
    if(!cache.get(identity,projection_input,In,destination,Out,raised)) {
        asm volatile("fsflags zero":::"memory");
        const bool eligible=m4_produce(projection_input,destination,K);
        asm volatile("frflags %0":"=r"(raised)::"memory");
        const unsigned restored=(before&31)|raised;
        asm volatile("fsflags %0"::"r"(restored):"memory");
        if(!eligible || !cache.put(identity,projection_input,In,destination,Out,raised)) return false;
    }
    const unsigned restored=(before&31)|raised;
    asm volatile("fsflags %0"::"r"(restored):"memory");
    return true;
}
int main() {
    unsigned errors=0;
    for(unsigned trial=0;trial<4;++trial) {
        const bool reuse=trial==1 || trial==2;
        std::memset(output,0xa5,sizeof(output));
        value_cache<> cache;
        asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0"::"r"(17):"memory");
        const uint64_t begin=cycle();
        bool used=true;
        uint64_t phase[3];unsigned flags[3],vector_flags[3];
        for(unsigned call=0;call<3;++call) {
            used&=reuse ? prepare(cache,output[call]+64):m4_produce(projection_input,output[call]+64,K);
            flags[call]=fc();vector_flags[call]=vc();phase[call]=cycle();
        }
        const uint64_t finished=phase[2];
        unsigned local=!used;
        for(unsigned call=0;call<3;++call) {
            local+=flags[call]!=17 || vector_flags[call]!=5;
            local+=std::memcmp(output[call]+64,projection_golden,Out)!=0;
            for(unsigned j=0;j<64;++j)
                local+=output[call][j]!=0xa5 || output[call][64+Out+j]!=0xa5;
        }
        const auto &s=cache.statistics();
        local+=s.hits!=(reuse?2u:0u) || s.misses!=(reuse?1u:0u) ||
            s.stores!=(reuse?1u:0u) || s.conflicts || s.allocation_failures;
        errors+=local;
        printf("M4_CACHE_SOC_TRIAL id=%u reuse=%u first=%lu second=%lu third=%lu total=%lu "
               "hits=%lu misses=%lu stores=%lu compare_requested=%lu copied=%lu errors=%u\n",
               trial,unsigned(reuse),(unsigned long)(phase[0]-begin),
               (unsigned long)(phase[1]-phase[0]),(unsigned long)(phase[2]-phase[1]),
               (unsigned long)(finished-begin),(unsigned long)s.hits,(unsigned long)s.misses,
               (unsigned long)s.stores,(unsigned long)s.comparison_bytes_requested,
               (unsigned long)s.copied_payload_bytes,local);
    }
    printf("M4_CACHE_SOC_RESULT errors=%u trials=4 calls=12 m=4 k=1536\n",errors);
    return errors?1:0;
}
