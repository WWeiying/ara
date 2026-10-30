#include "q8_K-prepared-cache.h"
#include "../m4_group_sums/quantizer_candidate.h"
#include "printf.h"
#include <cstring>

extern "C" const float sums_input[];
extern "C" const unsigned char sums_golden[];
static constexpr size_t K=1536, In=24576, Out=7008;
alignas(64) static unsigned char output[3][Out+128], input_copy[In];
alignas(64) static unsigned char heap[128*1024];
extern "C" void *_sbrk(ptrdiff_t increment) {
    static size_t used=0;
    if(increment<0 || size_t(increment)>sizeof(heap)-used)
        return reinterpret_cast<void *>(-1);
    void *p=heap+used;used+=size_t(increment);return p;
}
static uint64_t cycle() {
    uint64_t c;asm volatile("fence rw,rw;rdcycle %0":"=r"(c)::"memory");return c;
}
static unsigned fcsr() {
    unsigned c;asm volatile("frcsr %0":"=r"(c)::"memory");return c;
}
static bool produce(void *dst,unsigned &raised) {
    const unsigned before=fcsr();
    asm volatile("fsflags zero":::"memory");
    const bool ok=qbs_m4_parallel_sums::quantize(sums_input,dst,K);
    asm volatile("frflags %0":"=r"(raised)::"memory");
    const unsigned restored=(before&31)|raised;
    asm volatile("fsflags %0"::"r"(restored):"memory");return ok;
}
int main() {
    using namespace ggml_riscv_q8_K_cache;
    ggml_riscv_byte_ops::copy(input_copy,sums_input,In);
    unsigned errors=0,reference_flags=0;
    printf("CACHE_COST_SCOPE rows=4 k=1536 bytes=7008 calls=3 trials=4 matrix=0\n");
    for(unsigned trial=0;trial<4;++trial) {
        const bool reuse=trial==1 || trial==2;
        std::memset(output,0xa5,sizeof(output));
        value_cache<> cache;
        key identity;identity.k=K;identity.producer_tag=3;
        unsigned local=0,producers=0;
        uint64_t steps[3]={};
        asm volatile("csrwi fcsr,17;csrwi vcsr,5;csrwi vstart,0":::"memory");
        const uint64_t start=cycle();
        for(unsigned part=0;part<3;++part) {
            const uint64_t begin=cycle();
            unsigned raised=0;const unsigned before=fcsr();
            void *dst=output[part]+64;
            if(!reuse || !cache.get(identity,sums_input,In,dst,Out,raised)) {
                ++producers;
                local+=!produce(dst,raised);
                if(reuse && part<2) local+=!cache.put(identity,sums_input,In,dst,Out,raised);
            }
            const unsigned restored=(before&31)|raised;
            asm volatile("fsflags %0"::"r"(restored):"memory");
            if(reuse && part==2) cache.clear();
            steps[part]=cycle()-begin;
        }
        const uint64_t total=cycle()-start;
        const unsigned flags=fcsr();unsigned vc;
        asm volatile("csrr %0,vcsr":"=r"(vc)::"memory");
        if(!trial) reference_flags=flags;
        local+=flags!=reference_flags || (flags&17)!=17 || flags>31 || vc!=5;
        const auto &stats=cache.statistics();
        local+=producers!=(reuse?1u:3u) || stats.hits!=(reuse?2u:0u) ||
            stats.misses!=(reuse?1u:0u) || stats.stores!=(reuse?1u:0u) ||
            stats.conflicts || stats.rejected || stats.allocation_failures || cache.size();
        uint64_t signature=UINT64_C(14695981039346656037);
        for(unsigned part=0;part<3;++part) {
            for(unsigned i=0;i<Out;++i) {
                local+=output[part][64+i]!=sums_golden[i];
                signature=(signature^output[part][64+i])*UINT64_C(1099511628211);
            }
            for(unsigned i=0;i<64;++i)
                local+=output[part][i]!=0xa5 || output[part][64+Out+i]!=0xa5;
        }
        local+=!ggml_riscv_byte_ops::equal(sums_input,input_copy,In);
        errors+=local;
        printf("CACHE_COST_TRIAL id=%u reuse=%u total=%lu first=%lu second=%lu third=%lu "
            "producers=%u hits=%lu misses=%lu stores=%lu compare_bytes=%lu copied_bytes=%lu "
            "fcsr=%u vcsr=%u errors=%u signature=%016lx\n",trial,unsigned(reuse),
            (unsigned long)total,(unsigned long)steps[0],(unsigned long)steps[1],
            (unsigned long)steps[2],producers,(unsigned long)stats.hits,
            (unsigned long)stats.misses,(unsigned long)stats.stores,
            (unsigned long)stats.comparison_bytes_requested,
            (unsigned long)stats.copied_payload_bytes,flags,vc,local,(unsigned long)signature);
        if(local) return 1;
    }
    printf("CACHE_COST_RESULT trials=4 errors=%u\n",errors);
    return errors?1:0;
}
