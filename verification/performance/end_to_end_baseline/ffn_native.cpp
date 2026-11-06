#include "qbs/qbs.h"
#include "q8_K-m4-packed.h"
#include "printf.h"
#include <cmath>
#include <cstring>

extern "C" const float ffn_input[], down_input[], ffn_0_expected[], ffn_1_expected[], ffn_2_expected[];
extern "C" const unsigned char ffn_quantized[], down_quantized[], ffn_0_weights[], ffn_1_weights[], ffn_2_weights[];
extern "C" const unsigned ffn_profiles[], ffn_0_flags[], ffn_1_flags[], ffn_2_flags[];
enum : unsigned { M=4, N=128, MaxPacked=24*4*QBS_Q8_K_BLOCK_BYTES };
alignas(64) static unsigned char activation[2][MaxPacked+128];
alignas(64) static float output[3][M*N+32];
static unsigned commands;
static uint64_t cycle() { uint64_t x; asm volatile("fence rw,rw;rdcycle %0":"=r"(x)::"memory"); return x; }
static unsigned fcsr() { unsigned x; asm volatile("frcsr %0":"=r"(x)::"memory"); return x; }
static unsigned vcsr() { unsigned x; asm volatile("csrr %0,vcsr":"=r"(x)::"memory"); return x; }
static unsigned checksum(const void *data, size_t bytes) {
    const auto *p=static_cast<const unsigned char *>(data); unsigned hash=2166136261u;
    for (size_t i=0; i<bytes; ++i) hash=(hash^p[i])*16777619u;
    return hash;
}
static qbs_status_t execute(void *, const qbs_descriptor_t *d, unsigned m, const void *a,
                           float *o, size_t stride, unsigned n, int segmented) {
    ++commands; return qbs_native_execute_command(nullptr,d,m,a,o,stride,n,segmented);
}
int main() {
    qbs_device_t device{};
    if (qbs_device_query(qbs_native_info,nullptr,&device)!=QBS_STATUS_OK) {
        printf("FFN_NATIVE_FAIL reason=device\n"); return 1;
    }
    const unsigned k[]={2048,2048,6144};
    const unsigned char *weights[]={ffn_0_weights,ffn_1_weights,ffn_2_weights};
    const float *expected[]={ffn_0_expected,ffn_1_expected,ffn_2_expected};
    const unsigned *flags[]={ffn_0_flags,ffn_1_flags,ffn_2_flags};
    uint64_t prep[2]{},admit[3]{},exec[3]{};
    unsigned prep_fc[2]{},observed_fc[3]{},observed_vc[3]{};
    bool prepared[2]{};
    std::memset(activation,0xa5,sizeof(activation)); std::memset(output,0xa5,sizeof(output));
    asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
    printf("FFN_NATIVE_SCOPE m=4 n=128 k0=2048 k1=2048 k2=6144 trials=1 parts=3 shared_gate_up_preparation=1 full_ggml=0\n");
    unsigned errors=0; const uint64_t begin=cycle();
    for (unsigned part=0; part<3; ++part) {
        const unsigned stage=part==2;
        if (part!=1) {
            const uint64_t a=cycle();
            prepared[stage]=ggml_riscv_q8_K_m4_packed::quantize<true>(stage?down_input:ffn_input,activation[stage]+64,k[part]);
            prep[stage]=cycle()-a; prep_fc[stage]=fcsr();
        }
        const size_t bytes=N*(k[part]/256)*(ffn_profiles[part]==QBS_WEIGHT_PROFILE_Q4_K?144:210);
        qbs_problem_t problem={static_cast<uint8_t>(ffn_profiles[part]),QBS_ACTIVATION_PROFILE_Q8_K,
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,QBS_ACTIVATION_STORAGE_M4_GROUPED,M,N,k[part]};
        qbs_plan_t plan{}; const uint64_t a=cycle();
        const auto admitted=qbs_plan_create(&device,&problem,&plan); const uint64_t b=cycle();
        const auto status=admitted==QBS_STATUS_OK?
            qbs_execute(&plan,weights[part],bytes,activation[stage]+64,(k[part]/256)*4*QBS_Q8_K_BLOCK_BYTES,
                        output[part]+16,M*N,N,nullptr,0,execute,nullptr):admitted;
        const uint64_t c=cycle(); admit[part]=b-a; exec[part]=c-b;
        observed_fc[part]=fcsr(); observed_vc[part]=vcsr();
        errors+=admitted!=QBS_STATUS_OK || status!=QBS_STATUS_OK || plan.command_m!=4 || plan.command_n!=32 ||
                plan.k_blocks!=k[part]/256 || plan.split_k || plan.uses_wide_m || qbs_plan_supports_activation_context(&plan);
    }
    const uint64_t end=cycle();
    const unsigned char *packed[]={ffn_quantized,down_quantized};
    for (unsigned stage=0; stage<2; ++stage) {
        const size_t size=(stage?24:8)*4*QBS_Q8_K_BLOCK_BYTES;
        const unsigned wanted_prep=stage?(9|*flags[0]|*flags[1]):9;
        errors+=!prepared[stage] || prep_fc[stage]!=wanted_prep || std::memcmp(activation[stage]+64,packed[stage],size)!=0;
        for (unsigned i=0; i<64; ++i) errors+=activation[stage][i]!=0xa5;
        for (size_t i=64+size; i<sizeof(activation[stage]); ++i) errors+=activation[stage][i]!=0xa5;
        printf("FFN_NATIVE_PREP stage=%u k=%u cycles=%lu fcsr=%u valid=%u checksum=%u\n",stage,stage?6144:2048,
            (unsigned long)prep[stage],prep_fc[stage],unsigned(prepared[stage]),checksum(activation[stage]+64,size));
    }
    unsigned wanted=9;
    for (unsigned part=0; part<3; ++part) {
        wanted|=*flags[part];
        unsigned local=std::memcmp(output[part]+16,expected[part],M*N*sizeof(float))!=0;
        for (unsigned i=0; i<M*N; ++i) local+=!std::isfinite(output[part][16+i]);
        const auto *raw=reinterpret_cast<const unsigned char *>(output[part]);
        for (unsigned i=0; i<64; ++i) local+=raw[i]!=0xa5 || raw[64+M*N*4+i]!=0xa5;
        local+=observed_fc[part]!=wanted || observed_vc[part]!=5; errors+=local;
        printf("FFN_NATIVE_PART part=%u profile=%u k=%u admission=%lu execution=%lu fcsr=%u vcsr=%u checksum=%u errors=%u\n",
            part,ffn_profiles[part],k[part],(unsigned long)admit[part],(unsigned long)exec[part],
            observed_fc[part],observed_vc[part],checksum(output[part]+16,M*N*sizeof(float)),local);
    }
    errors+=commands!=12;
    printf("FFN_NATIVE_RESULT preparation=%lu admission=%lu execution=%lu region=%lu commands=%u outputs=1536 errors=%u\n",
        (unsigned long)(prep[0]+prep[1]),(unsigned long)(admit[0]+admit[1]+admit[2]),
        (unsigned long)(exec[0]+exec[1]+exec[2]),(unsigned long)(end-begin),commands,errors);
    return errors?1:0;
}
