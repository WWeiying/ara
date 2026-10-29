#include "q8_K-prepared-cache.h"
#include "qbs/qbs.h"
#ifdef PROJECTION_LINUX
#include <cstdio>
#else
#include "printf.h"
#endif
#include <cmath>
#include <cstdlib>
#include <cstring>

extern "C" bool sums_current_produce(const float *,void *,int64_t);
extern "C" bool sums_parallel_produce(const float *,void *,int64_t);
static bool use_parallel=false;
extern "C" const float projection_input[],q_expected[],v_expected[],k_expected[];
extern "C" const unsigned char projection_input_reference[],projection_golden[];
extern "C" const unsigned char q_weights[],v_weights[],k_weights[];
extern "C" const unsigned char q_weights_reference[],v_weights_reference[],k_weights_reference[];
static constexpr size_t K=1536,In=24576,Out=7008;
alignas(64) static unsigned char packed[3][Out+128];
alignas(64) static float output[8192+32],reference[8192];
#ifndef PROJECTION_LINUX
alignas(64) static unsigned char heap[128*1024];
extern "C" void *_sbrk(ptrdiff_t increment) {
    static size_t used=0;
    if(increment<0 || size_t(increment)>sizeof(heap)-used) return reinterpret_cast<void *>(-1);
    void *p=heap+used;used+=size_t(increment);return p;
}
#endif
static uint64_t cycle() {
#ifdef PROJECTION_LINUX
    static uint64_t ordinal=0;return ++ordinal;
#else
    uint64_t x;asm volatile("fence rw,rw;rdcycle %0":"=r"(x)::"memory");return x;
#endif
}
static unsigned fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static bool prepare(ggml_riscv_q8_K_cache::value_cache<> &cache,void *destination,bool fill) {
    const unsigned before=fc();unsigned start;
    asm volatile("csrr %0,vstart":"=r"(start)::"memory");
    if((before>>5)!=0 || start) return false;
    ggml_riscv_q8_K_cache::key key;key.k=K;key.producer_tag=1;
    unsigned raised=0;
    if(!cache.get(key,projection_input,In,destination,Out,raised)) {
        asm volatile("fsflags zero":::"memory");
        const bool used=use_parallel?sums_parallel_produce(projection_input,destination,K):sums_current_produce(projection_input,destination,K);
        asm volatile("frflags %0":"=r"(raised)::"memory");
        const unsigned restored=(before&31)|raised;
        asm volatile("fsflags %0"::"r"(restored):"memory");
        if(!used) return false;
        if(fill && !cache.put(key,projection_input,In,destination,Out,raised)) return false;
    }
    const unsigned restored=(before&31)|raised;
    asm volatile("fsflags %0"::"r"(restored):"memory");return true;
}
static bool integrity() {
    return projection_input_reference!=reinterpret_cast<const unsigned char *>(projection_input) &&
        ggml_riscv_byte_ops::equal(projection_input,projection_input_reference,In) &&
        ggml_riscv_byte_ops::equal(q_weights,q_weights_reference,1327104) &&
        ggml_riscv_byte_ops::equal(v_weights,v_weights_reference,322560) &&
        ggml_riscv_byte_ops::equal(k_weights,k_weights_reference,221184);
}
int main() {
    qbs_device_t device{};unsigned errors=0;
    if(qbs_device_query(qbs_native_info,nullptr,&device)!=QBS_STATUS_OK || !integrity()) {
        printf("M4_SUMS_QKV_FAIL reason=admission_or_inputs\n");return 1;
    }
    const unsigned n[3]={1536,256,256},bytes[3]={1327104,322560,221184},offset[3]={0,6144,7168};
    const unsigned char *weights[3]={q_weights,v_weights,k_weights};
    const float *expected[3]={q_expected,v_expected,k_expected};
    printf("M4_SUMS_QKV_SCOPE reuse_both=1 cold_producer_only=1\n");
    unsigned reference_fc=0,reference_vc=0;
    for(unsigned trial=0;trial<4;++trial) {
        const bool candidate=trial==1 || trial==2;
        const bool reuse=true;use_parallel=candidate;
        std::memset(packed,0xa5,sizeof(packed));std::memset(output,0xa5,sizeof(output));
        ggml_riscv_q8_K_cache::value_cache<> cache;
        asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0"::"r"(17):"memory");
        uint64_t admit=0,prep=0,execute=0;unsigned local=0;
        const uint64_t begin=cycle();
        for(unsigned part=0;part<3;++part) {
            qbs_problem_t problem={part==1 ? QBS_WEIGHT_PROFILE_Q6_K:QBS_WEIGHT_PROFILE_Q4_K,
                QBS_ACTIVATION_PROFILE_Q8_K,QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                QBS_ACTIVATION_STORAGE_M4_GROUPED,4,n[part],K};
            qbs_plan_t plan{};const uint64_t a=cycle();
            const auto admission=qbs_plan_create_segmented_r4(&device,&problem,256,&plan);
            const uint64_t b=cycle();
            const bool used=reuse ? prepare(cache,packed[part]+64,part<2):false;
            // The known chain ends at K; include release rather than retaining a warm cache.
            if(reuse && part==2) cache.clear();
            const uint64_t c=cycle();
            const auto status=qbs_execute(&plan,weights[part],bytes[part],packed[part]+64,Out,
                output+16+offset[part],4*n[part],n[part],nullptr,0,qbs_native_execute_command,nullptr);
            const uint64_t d=cycle();
            admit+=b-a;prep+=c-b;execute+=d-c;
            local+=admission!=QBS_STATUS_OK || status!=QBS_STATUS_OK || !used ||
                   plan.command_m!=4 || plan.command_n!=32 || plan.k_blocks!=6 ||
                   plan.split_k || plan.uses_wide_m || qbs_plan_supports_activation_context(&plan);
        }
        const uint64_t end=cycle();const unsigned final_fc=fc(),final_vc=vc();
        const auto &stats=cache.statistics();
        local+=stats.hits!=(reuse?2u:0u) || stats.misses!=(reuse?1u:0u) ||
            stats.stores!=(reuse?1u:0u) || stats.conflicts || stats.allocation_failures;
        for(unsigned part=0;part<3;++part) {
            local+=!ggml_riscv_byte_ops::equal(packed[part]+64,projection_golden,Out);
            for(unsigned i=0;i<64;++i) local+=packed[part][i]!=0xa5 || packed[part][64+Out+i]!=0xa5;
            for(unsigned i=0;i<4*n[part];++i) {
                const float actual=output[16+offset[part]+i],want=expected[part][i];
                const float atol=part==0 ? 2e-4f:2e-3f,rtol=part==0 ? 2e-5f:2e-3f;
                local+=!std::isfinite(actual) || !std::isfinite(want) ||
                    std::fabs(actual-want)>atol+rtol*std::fabs(want);
            }
        }
        if(!trial) {ggml_riscv_byte_ops::copy(reference,output+16,sizeof(reference));reference_fc=final_fc;reference_vc=final_vc;}
        local+=!ggml_riscv_byte_ops::equal(reference,output+16,sizeof(reference)) ||
            final_fc!=reference_fc || final_vc!=reference_vc;
        const auto *raw=reinterpret_cast<const unsigned char *>(output);
        for(unsigned i=0;i<64;++i) local+=raw[i]!=0xa5 || raw[64+sizeof(reference)+i]!=0xa5;
        errors+=local;
        printf("M4_SUMS_QKV_TRIAL id=%u candidate=%u admit=%lu prep=%lu execute=%lu total=%lu "
               "hits=%lu misses=%lu stores=%lu fcsr=%u vcsr=%u errors=%u\n",trial,unsigned(candidate),
               (unsigned long)admit,(unsigned long)prep,(unsigned long)execute,(unsigned long)(end-begin),
               (unsigned long)stats.hits,(unsigned long)stats.misses,(unsigned long)stats.stores,final_fc,final_vc,local);
    }
    errors+=!integrity();
#ifdef PROJECTION_LINUX
    printf("M4_SUMS_QKV_FUNCTIONAL_RESULT errors=%u trials=4 m=4 k=1536 outputs=8192 commands=256\n",errors);
#else
    printf("M4_SUMS_QKV_RESULT errors=%u trials=4 m=4 k=1536 outputs=8192 commands=256\n",errors);
#endif
    return errors ? 1:0;
}
