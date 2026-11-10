#include "q8_K-prepared-cache.h"
#include "qbs/qbs.h"
#include "printf.h"
#include <cmath>
#include <cstdlib>
#include <cstring>

extern "C" bool stage4_baseline_produce(const float *,void *,int64_t);
extern "C" bool stage4_candidate_produce(const float *,void *,int64_t);
extern "C" const float projection_input[],q_expected[],v_expected[],k_expected[];
extern "C" const unsigned char projection_input_reference[],projection_golden[];
extern "C" const unsigned char q_weights[],v_weights[],k_weights[];
extern "C" const unsigned char q_weights_reference[],v_weights_reference[],k_weights_reference[];
extern "C" const unsigned char ordered_golden[];
static constexpr size_t K=1536,InputBytes=24576,PackedBytes=7008,Outputs=8192;
static constexpr unsigned Trials=4;
alignas(64) static unsigned char packed[3][PackedBytes+128];
alignas(64) static float output[Outputs+32],reference[Outputs];
alignas(64) static unsigned char heap[128*1024];
extern "C" void *_sbrk(ptrdiff_t increment) {
    static size_t used=0;
    if(increment<0 || size_t(increment)>sizeof(heap)-used) return reinterpret_cast<void *>(-1);
    void *result=heap+used;used+=size_t(increment);return result;
}

static uint64_t cycle() {
    uint64_t value;asm volatile("fence rw,rw;rdcycle %0":"=r"(value)::"memory");return value;
}
static unsigned fcsr() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vcsr() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static unsigned vstart() {unsigned x;asm volatile("csrr %0,vstart":"=r"(x)::"memory");return x;}
static uint64_t hash_bytes(const void *pointer,size_t n) {
    const auto *p=static_cast<const volatile unsigned char *>(pointer);
    uint64_t value=UINT64_C(14695981039346656037);
    for(size_t i=0;i<n;++i) value=(value^p[i])*UINT64_C(1099511628211);
    return value;
}
static bool integrity() {
    return projection_input_reference!=reinterpret_cast<const unsigned char *>(projection_input) &&
        ggml_riscv_byte_ops::equal(projection_input,projection_input_reference,InputBytes) &&
        ggml_riscv_byte_ops::equal(q_weights,q_weights_reference,1327104) &&
        ggml_riscv_byte_ops::equal(v_weights,v_weights_reference,322560) &&
        ggml_riscv_byte_ops::equal(k_weights,k_weights_reference,221184);
}

struct cache_owner {
    ggml_riscv_q8_K_cache::value_cache<> bytes;
    unsigned producers=0;
    bool candidate;
    bool prepare(void *destination,bool fill) {
        const unsigned before=fcsr();
        if((before>>5)!=0 || vstart()) return false;
        ggml_riscv_q8_K_cache::key key;
        key.k=K;key.producer_tag=candidate?4u:3u;
        unsigned raised=0;
        if(!bytes.get(key,projection_input,InputBytes,destination,PackedBytes,raised)) {
            // Preserve the production cache's independent raised-flags snapshot.
            asm volatile("fsflags zero":::"memory");
            const bool vector=candidate
                ?stage4_candidate_produce(projection_input,destination,K)
                :stage4_baseline_produce(projection_input,destination,K);
            asm volatile("frflags %0":"=r"(raised)::"memory");
            const unsigned restored=(before&31)|raised;
            asm volatile("fsflags %0"::"r"(restored):"memory");
            ++producers;
            // False means generic already completed, never retry the producer.
            if(!vector) return false;
            if(fill && !bytes.put(key,projection_input,InputBytes,destination,PackedBytes,raised)) return false;
        }
        const unsigned restored=(before&31)|raised;
        asm volatile("fsflags %0"::"r"(restored):"memory");
        return true;
    }
};

int main() {
    qbs_device_t device{};
    if(qbs_device_query(qbs_native_info,nullptr,&device)!=QBS_STATUS_OK || !integrity()) {
        printf("STAGE4_CHAIN_FAIL reason=admission_or_input\n");return 1;
    }
    const unsigned widths[3]={1536,256,256},sizes[3]={1327104,322560,221184},offsets[3]={0,6144,7168};
    const unsigned char *weights[3]={q_weights,v_weights,k_weights};
    const float *captured[3]={q_expected,v_expected,k_expected};
    uint64_t errors=0;
    printf("STAGE4_CHAIN_SCOPE trials=4 m=4 k=1536 q=1536 v=256 key=256 cache_both=1 parallel_both=1 full_ggml=0\n");
    for(unsigned trial=0;trial<Trials;++trial) {
        const bool candidate=trial==1 || trial==2;
        std::memset(packed,0xa5,sizeof(packed));std::memset(output,0xa5,sizeof(output));
        cache_owner cache;cache.candidate=candidate;
        // Caller setup is outside the SDK-chain interval; cache flag replay is inside.
        asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0"::"r"(17):"memory");
        uint64_t admit=0,prep=0,execute=0,local=0;
        const uint64_t begin=cycle();
        for(unsigned part=0;part<3;++part) {
            const qbs_problem_t problem={part==1?QBS_WEIGHT_PROFILE_Q6_K:QBS_WEIGHT_PROFILE_Q4_K,
                QBS_ACTIVATION_PROFILE_Q8_K,QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                QBS_ACTIVATION_STORAGE_M4_GROUPED,4,widths[part],K};
            qbs_plan_t plan{};const uint64_t a=cycle();
            const auto admission=qbs_plan_create_segmented_r4(&device,&problem,256,&plan);
            const uint64_t b=cycle();
            const bool prepared=cache.prepare(packed[part]+64,part<2);
            if(part==2) cache.bytes.clear();
            const uint64_t c=cycle();
            if(admission!=QBS_STATUS_OK || !prepared || plan.command_m!=4 || plan.command_n!=32 ||
               plan.k_blocks!=6 || plan.split_k || plan.uses_wide_m || qbs_plan_supports_activation_context(&plan)) {
                ++local;break;
            }
            const auto status=qbs_execute(&plan,weights[part],sizes[part],packed[part]+64,PackedBytes,
                output+16+offsets[part],4*widths[part],widths[part],nullptr,0,qbs_native_execute_command,nullptr);
            const uint64_t d=cycle();
            admit+=b-a;prep+=c-b;execute+=d-c;
            local+=status!=QBS_STATUS_OK;
            if(status!=QBS_STATUS_OK) break;
        }
        const uint64_t end=cycle();
        const unsigned final_fcsr=fcsr(),final_vcsr=vcsr(),final_vstart=vstart();
        const auto &stats=cache.bytes.statistics();
        local+=stats.queries!=3 || stats.hits!=2 || stats.misses!=1 || stats.stores!=1 ||
            stats.conflicts || stats.rejected || stats.evictions || stats.allocation_failures ||
            cache.producers!=1 || cache.bytes.retained_bytes()!=0 ||
            final_fcsr!=17 || final_vcsr!=5 || final_vstart!=0;
        for(unsigned part=0;part<3;++part) {
            local+=!ggml_riscv_byte_ops::equal(packed[part]+64,projection_golden,PackedBytes);
            for(unsigned i=0;i<64;++i) local+=packed[part][i]!=0xa5 || packed[part][64+PackedBytes+i]!=0xa5;
            for(unsigned i=0;i<4*widths[part];++i) {
                const float actual=output[16+offsets[part]+i],expected=captured[part][i];
                const float atol=part==0?2e-4f:2e-3f,rtol=part==0?2e-5f:2e-3f;
                local+=!std::isfinite(actual) || !std::isfinite(expected) ||
                    std::fabs(actual-expected)>atol+rtol*std::fabs(expected);
            }
        }
        // Unchanged ordered qbs_ref supplies this complete independent raw oracle.
        local+=!ggml_riscv_byte_ops::equal(output+16,ordered_golden,sizeof(reference));
        if(!trial) ggml_riscv_byte_ops::copy(reference,output+16,sizeof(reference));
        local+=!ggml_riscv_byte_ops::equal(reference,output+16,sizeof(reference));
        const auto *raw=reinterpret_cast<const unsigned char *>(output);
        for(unsigned i=0;i<64;++i) local+=raw[i]!=0xa5 || raw[64+sizeof(reference)+i]!=0xa5;
        errors+=local;
        printf("STAGE4_CHAIN_TRIAL id=%u candidate=%u tag=%u admit=%lu prep=%lu execute=%lu total=%lu queries=%lu hits=%lu misses=%lu stores=%lu producers=%u compared=%lu copied=%lu retained=%lu fcsr=%u vcsr=%u vstart=%u output_hash=%lx packed_hash=%lx errors=%lu\n",
            trial,unsigned(candidate),candidate?4u:3u,(unsigned long)admit,(unsigned long)prep,
            (unsigned long)execute,(unsigned long)(end-begin),(unsigned long)stats.queries,
            (unsigned long)stats.hits,(unsigned long)stats.misses,(unsigned long)stats.stores,
            cache.producers,(unsigned long)stats.comparison_bytes_requested,
            (unsigned long)stats.copied_payload_bytes,(unsigned long)cache.bytes.retained_bytes(),
            final_fcsr,final_vcsr,final_vstart,(unsigned long)hash_bytes(output+16,sizeof(reference)),
            (unsigned long)hash_bytes(packed[0]+64,PackedBytes),(unsigned long)local);
    }
    errors+=!integrity();
    printf("STAGE4_CHAIN_DONE trials=4 commands=256 outputs_per_trial=8192 errors=%lu\n",(unsigned long)errors);
    return errors?1:0;
}
