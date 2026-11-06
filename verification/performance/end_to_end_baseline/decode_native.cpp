#include "qbs/qbs.h"
#include "printf.h"
#include <cmath>
#include <cstring>

extern "C" void quantize_row_q8_K(const float *, void *, int64_t);
extern "C" const float decode_input_0[], decode_input_1[], decode_input_2[], decode_input_3[];
extern "C" const unsigned char decode_quantized_0[], decode_quantized_1[], decode_quantized_2[], decode_quantized_3[];
extern "C" const unsigned char decode_weights_0[], decode_weights_1[], decode_weights_2[], decode_weights_3[],
    decode_weights_4[], decode_weights_5[], decode_weights_6[];
extern "C" const float decode_expected_0[], decode_expected_1[], decode_expected_2[], decode_expected_3[],
    decode_expected_4[], decode_expected_5[], decode_expected_6[];
extern "C" const unsigned decode_profiles[], decode_flags[];

enum : unsigned { N=128, Parts=7, Stages=4, MaxActivation=24*QBS_Q8_K_BLOCK_BYTES };
alignas(64) static unsigned char activation[Stages][MaxActivation+128];
alignas(64) static float output[Parts][N+32];
static unsigned commands, command_errors;
static uint64_t cycle() { uint64_t x; asm volatile("fence rw,rw;rdcycle %0":"=r"(x)::"memory"); return x; }
static unsigned fcsr() { unsigned x; asm volatile("frcsr %0":"=r"(x)::"memory"); return x; }
static unsigned vcsr() { unsigned x; asm volatile("csrr %0,vcsr":"=r"(x)::"memory"); return x; }
static unsigned vstart() { unsigned x; asm volatile("csrr %0,vstart":"=r"(x)::"memory"); return x; }
static unsigned checksum(const void *data,size_t size) {
    const auto *p=static_cast<const unsigned char *>(data); unsigned hash=2166136261u;
    for (size_t i=0;i<size;++i) hash=(hash^p[i])*16777619u;
    return hash;
}
static qbs_status_t execute(void *,const qbs_descriptor_t *descriptor,unsigned m,const void *a,
                           float *o,size_t stride,unsigned n,int segmented) {
    ++commands;
    command_errors+=m!=1 || n!=32 || segmented;
    return qbs_native_execute_command(nullptr,descriptor,m,a,o,stride,n,segmented);
}

int main() {
    qbs_device_t device{};
    if (qbs_device_query(qbs_native_info,nullptr,&device)!=QBS_STATUS_OK ||
        device.capabilities.activation_context_generation_bits<2) {
        printf("DECODE_NATIVE_FAIL reason=device\n"); return 1;
    }
    // Follow the actual first-layer scheduling: Q, V, K, gate, up, down, then the captured output head.
    const unsigned k[]={2048,2048,2048,2048,2048,6144,2048};
    const unsigned stage[]={0,0,0,1,1,2,3};
    const unsigned scope[]={1,2,3,1,3,0,0};
    const unsigned generation[]={1,1,1,2,2,0,3};
    const float *inputs[]={decode_input_0,decode_input_1,decode_input_2,decode_input_3};
    const unsigned char *packed[]={decode_quantized_0,decode_quantized_1,decode_quantized_2,decode_quantized_3};
    const unsigned char *weights[]={decode_weights_0,decode_weights_1,decode_weights_2,decode_weights_3,
        decode_weights_4,decode_weights_5,decode_weights_6};
    const float *expected[]={decode_expected_0,decode_expected_1,decode_expected_2,decode_expected_3,
        decode_expected_4,decode_expected_5,decode_expected_6};
    uint64_t prep[Stages]{},admit[Parts]{},exec[Parts]{};
    unsigned prep_fc[Stages]{},prep_vc[Stages]{},prep_vs[Stages]{},before_fc[Stages]{},observed_fc[Parts]{},observed_vc[Parts]{},observed_vs[Parts]{};
    unsigned admitted_status[Parts]{},execute_status[Parts]{};
    bool eligible[Parts]{};
    std::memset(activation,0xa5,sizeof(activation)); std::memset(output,0xa5,sizeof(output));
    asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
    printf("DECODE_NATIVE_SCOPE m=1 n=128 parts=7 stages=4 trials=1 full_k=1 full_n=0 full_ggml=0 context=production\n");
    unsigned errors=0; const uint64_t begin=cycle();
    for (unsigned part=0;part<Parts;++part) {
        const unsigned s=stage[part];
        if (part==0 || part==3 || part==5 || part==6) {
            before_fc[s]=fcsr(); const uint64_t start=cycle();
            quantize_row_q8_K(inputs[s],activation[s]+64,k[part]);
            prep[s]=cycle()-start; prep_fc[s]=fcsr(); prep_vc[s]=vcsr(); prep_vs[s]=vstart();
        }
        const size_t bytes=N*(k[part]/256)*(decode_profiles[part]==QBS_WEIGHT_PROFILE_Q4_K?144:210);
        qbs_problem_t problem={static_cast<uint8_t>(decode_profiles[part]),QBS_ACTIVATION_PROFILE_Q8_K,
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,QBS_ACTIVATION_STORAGE_ROW_MAJOR,1,N,k[part]};
        qbs_plan_t plan{}; const uint64_t a=cycle();
        const auto admitted=qbs_plan_create(&device,&problem,&plan);
        eligible[part]=qbs_plan_supports_activation_context(&plan);
        qbs_execution_options_t options{};
        options.use_activation_context=part!=5;
        options.activation_context.context_id=0;
        options.activation_context.generation=generation[part];
        options.activation_context_scope=scope[part];
        const uint64_t b=cycle();
        const auto status=admitted==QBS_STATUS_OK?
            qbs_execute_with_options(&plan,weights[part],bytes,activation[s]+64,(k[part]/256)*QBS_Q8_K_BLOCK_BYTES,
                output[part]+16,N,N,nullptr,0,&options,execute,nullptr):admitted;
        const uint64_t c=cycle(); admit[part]=b-a; exec[part]=c-b;
        admitted_status[part]=admitted; execute_status[part]=status;
        observed_fc[part]=fcsr(); observed_vc[part]=vcsr(); observed_vs[part]=vstart();
        errors+=admitted!=QBS_STATUS_OK || status!=QBS_STATUS_OK || plan.command_n!=32 ||
            plan.k_blocks!=k[part]/256 || plan.split_k || plan.uses_wide_m || eligible[part]!=(part!=5);
        if (admitted!=QBS_STATUS_OK || status!=QBS_STATUS_OK) break;
    }
    const uint64_t end=cycle();
    for (unsigned s=0;s<Stages;++s) {
        const size_t size=(s==2?24:8)*QBS_Q8_K_BLOCK_BYTES;
        errors+=prep_fc[s]!=(before_fc[s]|1) || prep_vc[s]!=3 || prep_vs[s]!=0 ||
            std::memcmp(activation[s]+64,packed[s],size)!=0;
        for (unsigned i=0;i<64;++i) errors+=activation[s][i]!=0xa5;
        for (size_t i=64+size;i<sizeof(activation[s]);++i) errors+=activation[s][i]!=0xa5;
        printf("DECODE_NATIVE_PREP stage=%u k=%u cycles=%lu before_fcsr=%u fcsr=%u vcsr=%u vstart=%u checksum=%u\n",
            s,s==2?6144:2048,(unsigned long)prep[s],before_fc[s],prep_fc[s],prep_vc[s],prep_vs[s],checksum(activation[s]+64,size));
    }
    unsigned wanted=9;
    for (unsigned part=0;part<Parts;++part) {
        wanted|=decode_flags[part];
        unsigned local=std::memcmp(output[part]+16,expected[part],N*sizeof(float))!=0;
        for (unsigned i=0;i<N;++i) local+=!std::isfinite(output[part][16+i]);
        const auto *raw=reinterpret_cast<const unsigned char *>(output[part]);
        for (unsigned i=0;i<64;++i) local+=raw[i]!=0xa5 || raw[64+N*4+i]!=0xa5;
        local+=observed_fc[part]!=wanted || observed_vc[part]!=3 || observed_vs[part]!=0; errors+=local;
        printf("DECODE_NATIVE_PART part=%u profile=%u k=%u context=%u scope=%u admission=%lu execution=%lu "
            "admitted=%u status=%u fcsr=%u vcsr=%u vstart=%u checksum=%u errors=%u\n",part,decode_profiles[part],k[part],
            unsigned(eligible[part]),scope[part],(unsigned long)admit[part],(unsigned long)exec[part],
            admitted_status[part],execute_status[part],observed_fc[part],observed_vc[part],observed_vs[part],checksum(output[part]+16,N*4),local);
    }
    uint64_t prep_sum=0,admit_sum=0,exec_sum=0;
    for (auto x:prep) prep_sum+=x;
    for (auto x:admit) admit_sum+=x;
    for (auto x:exec) exec_sum+=x;
    errors+=commands!=28 || command_errors;
    printf("DECODE_NATIVE_RESULT preparation=%lu admission=%lu execution=%lu region=%lu commands=%u outputs=896 errors=%u\n",
        (unsigned long)prep_sum,(unsigned long)admit_sum,(unsigned long)exec_sum,(unsigned long)(end-begin),commands,errors);
    return errors?1:0;
}
