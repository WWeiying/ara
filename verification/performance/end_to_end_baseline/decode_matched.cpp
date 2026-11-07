#include "qbs/qbs.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <cstring>

extern "C" {
void quantize_row_q8_K(const float *, void *, int64_t);
void ggml_gemv_q4_K_32x1_q8_K(int, float *, size_t, const void *, const void *, int, int);
void ggml_vec_dot_q6_K_q8_K(int, float *, size_t, const void *, size_t, const void *, size_t, int);
extern const float decode_input_0[],decode_input_1[],decode_input_2[],decode_input_3[];
extern const unsigned char decode_quantized_0[],decode_quantized_1[],decode_quantized_2[],decode_quantized_3[];
extern const unsigned char decode_weights_0[],decode_weights_1[],decode_weights_2[],decode_weights_3[],
    decode_weights_4[],decode_weights_5[],decode_weights_6[];
extern const unsigned char native_decode_weights_0[],native_decode_weights_1[],native_decode_weights_2[],
    native_decode_weights_3[],native_decode_weights_4[],native_decode_weights_5[],native_decode_weights_6[];
extern const unsigned char rvv_decode_expected_0[],rvv_decode_expected_1[],rvv_decode_expected_2[],
    rvv_decode_expected_3[],rvv_decode_expected_4[],rvv_decode_expected_5[],rvv_decode_expected_6[];
extern const float decode_expected_0[],decode_expected_1[],decode_expected_2[],decode_expected_3[],
    decode_expected_4[],decode_expected_5[],decode_expected_6[];
extern const unsigned decode_profiles[],decode_flags[];
}

enum : unsigned { N=64, Parts=7, Stages=4, Block=256, Q8Bytes=292, Q6Bytes=210, MaxActivation=24*Q8Bytes };
static constexpr unsigned K[Parts]={2048,2048,2048,2048,2048,6144,2048};
static constexpr unsigned Stage[Parts]={0,0,0,1,1,2,3};
static constexpr unsigned Profile[Parts]={1,2,1,1,1,2,2};
static constexpr unsigned Scope[Parts]={1,2,3,1,3,0,0};
static constexpr unsigned Generation[Parts]={1,1,1,2,2,0,3};
alignas(64) static unsigned char activation[Stages][MaxActivation+128];
alignas(64) static float output[Parts][N+32];
static qbs_device_t device;
static unsigned native_commands,native_bad,rvv_q4_calls,rvv_q6_calls;

struct State { unsigned fc,vc,vs; };
struct Call {
    bool native;
    unsigned part,k,profile;
    const unsigned char *weights;
    qbs_plan_t plan;
    qbs_execution_options_t options;
};

static uint64_t cycle() {
    uint64_t value;
    asm volatile("fence rw,rw;rdcycle %0" : "=r"(value) :: "memory");
    return value;
}
static State completed_state() {
    State value;
    // The vector CSR read waits for backend completion, including vector stores.
    asm volatile("csrr %0,vcsr" : "=r"(value.vc) :: "memory");
    asm volatile("frcsr %0" : "=r"(value.fc) :: "memory");
    asm volatile("csrr %0,vstart" : "=r"(value.vs) :: "memory");
    return value;
}
static unsigned checksum(const void *data,size_t bytes) {
    const auto *p=static_cast<const unsigned char *>(data);
    unsigned hash=2166136261u;
    for (size_t i=0;i<bytes;++i) hash=(hash^p[i])*16777619u;
    return hash;
}
static unsigned guards(const unsigned char *data,size_t used,size_t size) {
    unsigned errors=0;
    for (size_t i=0;i<64;++i) errors+=data[i]!=0xa5;
    for (size_t i=64+used;i<size;++i) errors+=data[i]!=0xa5;
    return errors;
}
static qbs_status_t native_command(void *,const qbs_descriptor_t *d,unsigned m,const void *a,
                                    float *o,size_t stride,unsigned n,int segmented) {
    ++native_commands; native_bad+=m!=1 || n!=32 || segmented;
    return qbs_native_execute_command(nullptr,d,m,a,o,stride,n,segmented);
}

static __attribute__((noinline)) qbs_status_t configure(Call *call,bool native,unsigned part,
                                                       const unsigned char *weights) {
    call->native=native;call->part=part;call->k=K[part];call->profile=decode_profiles[part];call->weights=weights;
    if (!native) return QBS_STATUS_OK;
    call->plan=qbs_plan_t{};
    call->options=qbs_execution_options_t{};
    qbs_problem_t problem={static_cast<uint8_t>(call->profile),QBS_ACTIVATION_PROFILE_Q8_K,
        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,QBS_ACTIVATION_STORAGE_ROW_MAJOR,1,N,call->k};
    const auto status=qbs_plan_create(&device,&problem,&call->plan);
    if (status!=QBS_STATUS_OK) return status;
    call->options.use_activation_context=part!=5;
    call->options.activation_context.context_id=0;
    call->options.activation_context.generation=Generation[part];
    call->options.activation_context_scope=Scope[part];
    return QBS_STATUS_OK;
}

static __attribute__((noinline)) qbs_status_t execute(const Call *call) {
    const unsigned part=call->part;
    const void *a=activation[Stage[part]]+64;
    float *o=output[part]+16;
    if (call->native) {
        const size_t bytes=N*(call->k/Block)*(call->profile==1?144:210);
        return qbs_execute_with_options(&call->plan,call->weights,bytes,a,(call->k/Block)*Q8Bytes,
                                       o,N,N,nullptr,0,&call->options,native_command,nullptr);
    }
    if (call->profile==1) {
        ++rvv_q4_calls;
        ggml_gemv_q4_K_32x1_q8_K(int(call->k),o,N*sizeof(float),call->weights,a,1,N);
    } else {
        rvv_q6_calls+=N;
        const size_t stride=(call->k/Block)*Q6Bytes;
        for (unsigned row=0;row<N;++row)
            ggml_vec_dot_q6_K_q8_K(int(call->k),o+row,0,call->weights+row*stride,0,a,0,1);
    }
    return QBS_STATUS_OK;
}

int main() {
    unsigned long vlenb;
    asm volatile("csrr %0,vlenb" : "=r"(vlenb));
    if (vlenb!=128 || qbs_device_query(qbs_native_info,nullptr,&device)!=QBS_STATUS_OK ||
        device.capabilities.activation_context_generation_bits<2) {
        printf("MATCHED_DECODE_FAIL reason=device\n");return 1;
    }
    for (unsigned p=0;p<Parts;++p) if (decode_profiles[p]!=Profile[p]) {
        printf("MATCHED_DECODE_FAIL reason=profile\n");return 1;
    }
    const float *inputs[Stages]={decode_input_0,decode_input_1,decode_input_2,decode_input_3};
    const unsigned char *packed[Stages]={decode_quantized_0,decode_quantized_1,decode_quantized_2,decode_quantized_3};
    const unsigned char *rvv_weights[Parts]={decode_weights_0,decode_weights_1,decode_weights_2,decode_weights_3,
        decode_weights_4,decode_weights_5,decode_weights_6};
    const unsigned char *native_weights[Parts]={native_decode_weights_0,native_decode_weights_1,native_decode_weights_2,
        native_decode_weights_3,native_decode_weights_4,native_decode_weights_5,native_decode_weights_6};
    const void *rvv_expected[Parts]={rvv_decode_expected_0,rvv_decode_expected_1,rvv_decode_expected_2,
        rvv_decode_expected_3,rvv_decode_expected_4,rvv_decode_expected_5,rvv_decode_expected_6};
    const void *native_expected[Parts]={decode_expected_0,decode_expected_1,decode_expected_2,
        decode_expected_3,decode_expected_4,decode_expected_5,decode_expected_6};
    const unsigned order[]={0,1,1,0};
    unsigned all_errors=0;
    printf("MATCHED_DECODE_SCOPE m=1 n=64 parts=7 stages=4 order=ABBA full_k=1 full_n=0 full_ggml=0 completion=csr_and_fence\n");
    for (unsigned trial=0;trial<4;++trial) {
        const bool native=order[trial];
        std::memset(activation,0xa5,sizeof(activation));std::memset(output,0xa5,sizeof(output));
        native_commands=native_bad=rvv_q4_calls=rvv_q6_calls=0;
        uint64_t prep[Stages]{},admission[Parts]{},execution[Parts]{};
        State prepared[Stages]{},finished[Parts]{};
        qbs_status_t admitted[Parts]{},status[Parts]{};
        unsigned completed=0;
        asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
        const uint64_t begin=cycle();
        for (unsigned p=0;p<Parts;++p) {
            const unsigned s=Stage[p];
            if (p==0 || p==3 || p==5 || p==6) {
                const uint64_t start=cycle();
                quantize_row_q8_K(inputs[s],activation[s]+64,K[p]);
                prepared[s]=completed_state();
                prep[s]=cycle()-start;
            }
            Call call;
            const uint64_t a=cycle();
            admitted[p]=configure(&call,native,p,native?native_weights[p]:rvv_weights[p]);
            const uint64_t b=cycle();
            status[p]=admitted[p]==QBS_STATUS_OK?execute(&call):admitted[p];
            finished[p]=completed_state();
            const uint64_t c=cycle();
            admission[p]=b-a;execution[p]=c-b;++completed;
            if (admitted[p]!=QBS_STATUS_OK || status[p]!=QBS_STATUS_OK) break;
        }
        const uint64_t region=cycle()-begin;
        // Both backends have identical completion observations above. All
        // comparison, payload hashing, guard checks and printing are untimed.
        unsigned errors=completed!=Parts;
        uint64_t preparation_sum=0,admission_sum=0,execution_sum=0;
        for (unsigned s=0;s<Stages;++s) {
            const size_t bytes=(s==2?24:8)*Q8Bytes;
            const unsigned local=std::memcmp(activation[s]+64,packed[s],bytes)!=0 ||
                guards(activation[s],bytes,sizeof(activation[s])) ||
                prepared[s].fc!=9 || prepared[s].vc!=3 || prepared[s].vs!=0 || prep[s]==0;
            errors+=local;preparation_sum+=prep[s];
            printf("MATCHED_DECODE_PREP trial=%u backend=%u stage=%u cycles=%lu fcsr=%u vcsr=%u vstart=%u checksum=%u errors=%u\n",
                   trial,unsigned(native),s,(unsigned long)prep[s],prepared[s].fc,prepared[s].vc,prepared[s].vs,
                   checksum(activation[s]+64,bytes),local);
        }
        unsigned wanted=9;
        for (unsigned p=0;p<Parts;++p) {
            if (native) wanted|=decode_flags[p];
            const unsigned local=std::memcmp(output[p]+16,native?native_expected[p]:rvv_expected[p],N*4)!=0 ||
                guards(reinterpret_cast<const unsigned char *>(output[p]),N*4,sizeof(output[p])) ||
                finished[p].fc!=wanted || finished[p].vc!=3 || finished[p].vs!=0 ||
                admitted[p]!=QBS_STATUS_OK || status[p]!=QBS_STATUS_OK ||
                admission[p]==0 || execution[p]==0;
            errors+=local;admission_sum+=admission[p];execution_sum+=execution[p];
            printf("MATCHED_DECODE_PART trial=%u backend=%u part=%u profile=%u k=%u admission=%lu execution=%lu fcsr=%u vcsr=%u vstart=%u checksum=%u errors=%u\n",
                   trial,unsigned(native),p,Profile[p],K[p],(unsigned long)admission[p],(unsigned long)execution[p],
                   finished[p].fc,finished[p].vc,finished[p].vs,checksum(output[p]+16,N*4),local);
        }
        errors+=native_bad || native_commands!=(native?14u:0u) || rvv_q4_calls!=(native?0u:4u) ||
            rvv_q6_calls!=(native?0u:192u) || region<preparation_sum+admission_sum+execution_sum;
        printf("MATCHED_DECODE_TRIAL trial=%u backend=%u preparation=%lu admission=%lu execution=%lu region=%lu commands=%u q4_calls=%u q6_calls=%u outputs=448 errors=%u\n",
               trial,unsigned(native),(unsigned long)preparation_sum,(unsigned long)admission_sum,
               (unsigned long)execution_sum,(unsigned long)region,native_commands,rvv_q4_calls,rvv_q6_calls,errors);
        all_errors+=errors;
        if (errors) return 1;
    }
    printf("MATCHED_DECODE_RESULT trials=4 native_commands=28 outputs_checked=1792 errors=%u\n",all_errors);
    return all_errors?1:0;
}
