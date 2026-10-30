#include "original_cache.h"
#include "hinted_cache.h"
#include "../m4_group_sums/quantizer_candidate.h"
#include "printf.h"
#include <cstring>

extern "C" const float sums_input[];
extern "C" const unsigned char sums_golden[];
static constexpr size_t K=1536, In=24576, Out=7008, Groups=3;
alignas(64) static unsigned char reference[Groups][Out+128];
alignas(64) static unsigned char output[3][Groups][Out+128],input_copy[Groups*In];
alignas(64) static unsigned char heap[512*1024];
static unsigned ref_flags[Groups];
static uint64_t reference_signature;
extern "C" void *_sbrk(ptrdiff_t increment) {
    static size_t used=0;
    if(increment<0 || size_t(increment)>sizeof(heap)-used)
        return reinterpret_cast<void *>(-1);
    void *p=heap+used;used+=size_t(increment);return p;
}
static uint64_t cycle() {
    uint64_t c;asm volatile("fence rw,rw;rdcycle %0":"=r"(c)::"memory");return c;
}
static unsigned flags() {
    unsigned c;asm volatile("frflags %0":"=r"(c)::"memory");return c;
}
static bool produce(unsigned group,void *dst,unsigned &raised) {
    const unsigned before=flags();
    asm volatile("fsflags zero":::"memory");
    const bool ok=qbs_m4_parallel_sums::quantize(sums_input+group*4*K,dst,K);
    raised=flags();
    const unsigned restored=before|raised;
    asm volatile("fsflags %0"::"r"(restored):"memory");return ok;
}
template<bool Hint,class Cache,class Key>
static unsigned trial(unsigned id,Cache &cache,Key key) {
    std::memset(output,0xa5,sizeof(output));
    unsigned errors=0,producers=0;
    asm volatile("csrwi fcsr,17;csrwi vcsr,5;csrwi vstart,0":::"memory");
    const uint64_t begin=cycle();
    size_t hints[Groups]={8,8,8};
    for(unsigned part=0;part<3;++part) {
        for(unsigned group=0;group<Groups;++group) {
            const auto *input=sums_input+group*4*K;
            auto *dst=output[part][group]+64;
            unsigned raised=0;const unsigned before=flags();bool hit;
            if constexpr(Hint) hit=cache.get(key,input,In,dst,Out,raised,&hints[group]);
            else hit=cache.get(key,input,In,dst,Out,raised);
            if(!hit) {
                ++producers;errors+=!produce(group,dst,raised);
                bool stored;
                if constexpr(Hint) stored=cache.put(key,input,In,dst,Out,raised,&hints[group]);
                else stored=cache.put(key,input,In,dst,Out,raised);
                errors+=!stored;
            }
            errors+=raised!=ref_flags[group];
            const unsigned restored=before|raised;
            asm volatile("fsflags %0"::"r"(restored):"memory");
        }
    }
    cache.clear();
    const uint64_t elapsed=cycle()-begin;
    unsigned fc,vc;
    asm volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
    unsigned expected_flags=17;
    for(unsigned group=0;group<Groups;++group) expected_flags|=ref_flags[group];
    errors+=fc!=expected_flags || vc!=5 || producers!=Groups;
    const auto &s=cache.statistics();
    errors+=s.queries!=9 || s.hits!=6 || s.misses!=3 || s.stores!=3 ||
        s.evictions || s.conflicts || s.rejected || s.allocation_failures || cache.size();
    // Full payload comparison remains outside the timed ROI. The input-derived
    // signature is computed once, not recomputed for every already-equal output.
    for(unsigned part=0;part<3;++part) for(unsigned group=0;group<Groups;++group) {
        errors+=!ggml_riscv_byte_ops::equal(output[part][group]+64,reference[group]+64,Out);
        for(unsigned i=0;i<64;++i)
            errors+=output[part][group][i]!=0xa5 || output[part][group][64+Out+i]!=0xa5;
    }
    errors+=!ggml_riscv_byte_ops::equal(sums_input,input_copy,Groups*In);
    printf("CACHE_HINT_TRIAL id=%u hint=%u total=%lu producers=%u hits=%lu misses=%lu "
        "stores=%lu compare_bytes=%lu copied_bytes=%lu fcsr=%u vcsr=%u errors=%u signature=%016lx\n",
        id,unsigned(Hint),(unsigned long)elapsed,producers,(unsigned long)s.hits,
        (unsigned long)s.misses,(unsigned long)s.stores,
        (unsigned long)s.comparison_bytes_requested,(unsigned long)s.copied_payload_bytes,
        fc,vc,errors,(unsigned long)reference_signature);
    return errors;
}
int main() {
    ggml_riscv_byte_ops::copy(input_copy,sums_input,Groups*In);
    std::memset(reference,0xa5,sizeof(reference));
    unsigned errors=0;
    for(unsigned group=0;group<Groups;++group) {
        asm volatile("csrwi fcsr,0;csrwi vcsr,5;csrwi vstart,0":::"memory");
        ggml_quantize_mat_q8_K_4x1_ara_generic(sums_input+group*4*K,reference[group]+64,K);
        ref_flags[group]=flags();
        for(unsigned i=0;i<64;++i)
            errors+=reference[group][i]!=0xa5 || reference[group][64+Out+i]!=0xa5;
    }
    errors+=!ggml_riscv_byte_ops::equal(reference[0]+64,sums_golden,Out);
    printf("CACHE_HINT_REFERENCE groups=3 errors=%u\n",errors);
    if(errors) return 1;
    reference_signature=UINT64_C(14695981039346656037);
    for(unsigned part=0;part<3;++part) for(unsigned group=0;group<Groups;++group)
        for(unsigned i=0;i<Out;++i)
            reference_signature=(reference_signature^reference[group][64+i])*UINT64_C(1099511628211);
    for(unsigned id=0;id<4;++id) {
        if(id==1 || id==2) {
            ggml_riscv_q8_K_cache_hint::value_cache<> cache;
            ggml_riscv_q8_K_cache_hint::key key;key.k=K;key.producer_tag=3;
            errors+=trial<true>(id,cache,key);
        } else {
            ggml_riscv_q8_K_cache::value_cache<> cache;
            ggml_riscv_q8_K_cache::key key;key.k=K;key.producer_tag=3;
            errors+=trial<false>(id,cache,key);
        }
        if(errors) return 1;
    }
    printf("CACHE_HINT_RESULT trials=4 errors=%u\n",errors);
    return errors?1:0;
}
