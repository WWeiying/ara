// Function/source-only driver. Builder must bind genuine GGML implementations,
// Q4 R32-packed weights and Q6 row-major weights from immutable inputs.
// Compile scalar validation without fast-math. No independent RVV oracle yet.
#include <stddef.h>
#include <stdint.h>
#include <cmath>
#include <cstring>
#include "printf.h"

extern "C" {
void quantize_row_q8_K(const float *, void *, int64_t);
void ggml_gemv_q4_K_32x1_q8_K(int, float *, size_t, const void *, const void *, int, int);
void ggml_vec_dot_q6_K_q8_K(int, float *, size_t, const void *, size_t, const void *, size_t, int);
extern const float decode_input_0[], decode_input_1[], decode_input_2[], decode_input_3[];
extern const unsigned char decode_quantized_0[], decode_quantized_1[], decode_quantized_2[], decode_quantized_3[];
extern const unsigned char decode_weights_0[], decode_weights_1[], decode_weights_2[], decode_weights_3[],
    decode_weights_4[], decode_weights_5[], decode_weights_6[];
extern const float decode_expected_0[], decode_expected_1[], decode_expected_2[], decode_expected_3[],
    decode_expected_4[], decode_expected_5[], decode_expected_6[];
extern const unsigned decode_profiles[];
}

enum : unsigned { N=128, Parts=7, Stages=4, BlockElements=256, Q8Bytes=292,
                  Q6Bytes=210, MaxActivation=24*Q8Bytes };
static constexpr unsigned PartK[Parts] = {2048,2048,2048,2048,2048,6144,2048};
static constexpr unsigned PartStage[Parts] = {0,0,0,1,1,2,3};
static constexpr unsigned Profiles[Parts] = {1,2,1,1,1,2,2};
static constexpr float Atol=2.0e-3f, Rtol=2.0e-3f;
alignas(64) static unsigned char activation[Stages][MaxActivation+128];
alignas(64) static float output[Parts][N+32];

struct State { unsigned fc, vc, vs; };
struct Dispatch {
    unsigned profile, k;
    size_t row_bytes;
    const void *weights;
    const void *activation;
    float *destination;
};
struct Metrics {
    unsigned errors=0, bit_differences=0, max_ulp=0;
    float max_abs=0.0f, max_rel=0.0f;
};

static uint64_t cycle() {
    uint64_t value;
    asm volatile("fence rw,rw;rdcycle %0" : "=r"(value) :: "memory");
    return value;
}
static State state() {
    State value;
    asm volatile("frcsr %0" : "=r"(value.fc) :: "memory");
    asm volatile("csrr %0,vcsr" : "=r"(value.vc) :: "memory");
    asm volatile("csrr %0,vstart" : "=r"(value.vs) :: "memory");
    return value;
}
static uint32_t bits(float value) {
    uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}
static bool finite_bits(uint32_t value) { return (value & 0x7f800000u) != 0x7f800000u; }
static uint32_t ordered_bits(uint32_t value) {
    return value & 0x80000000u ? ~value : value | 0x80000000u;
}
static unsigned ulp_distance(float actual, float expected) {
    if (actual == 0.0f && expected == 0.0f) return 0;
    const uint32_t a=ordered_bits(bits(actual)), b=ordered_bits(bits(expected));
    return a>b ? a-b : b-a;
}
static unsigned checksum(const void *data, size_t bytes) {
    const auto *p=static_cast<const unsigned char *>(data);
    unsigned hash=2166136261u;
    for (size_t i=0; i<bytes; ++i) hash=(hash^p[i])*16777619u;
    return hash;
}
static bool same_state(State a, State b) { return a.fc==b.fc && a.vc==b.vc && a.vs==b.vs; }
static bool fp_state_preserved(State before, State after) {
    // RNE remains selected; old sticky flags (including seeded DZ) cannot clear.
    return (before.fc & ~31u)==0 && (after.fc & ~31u)==0 &&
        ((after.fc & 31u) & (before.fc & 31u))==(before.fc & 31u) &&
        (before.fc & 8u)!=0 && (after.fc & 8u)!=0 && before.vs==0 && after.vs==0;
}

static __attribute__((noinline)) void prepare_dispatch(unsigned part, const void *weights, Dispatch *out) {
    out->profile=decode_profiles[part]; out->k=PartK[part];
    out->row_bytes=size_t(PartK[part]/BlockElements)*Q6Bytes;
    out->weights=weights; out->activation=activation[PartStage[part]]+64;
    out->destination=output[part]+16;
}

static __attribute__((noinline)) void execute_dispatch(const Dispatch *d) {
    if (d->profile==1) {
        // Genuine R32 kernel: one caller dispatch, all 128 output columns.
        ggml_gemv_q4_K_32x1_q8_K(int(d->k), d->destination, N*sizeof(float),
                                 d->weights, d->activation, 1, N);
    } else {
        const auto *weights=static_cast<const unsigned char *>(d->weights);
        for (unsigned row=0; row<N; ++row)
            ggml_vec_dot_q6_K_q8_K(int(d->k), d->destination+row, 0,
                                  weights+row*d->row_bytes, 0, d->activation, 0, 1);
    }
}

static __attribute__((noinline)) Metrics compare(unsigned part, const float *expected) {
    Metrics result;
    for (unsigned i=0; i<N; ++i) {
        const float actual=output[part][16+i], reference=expected[i];
        const uint32_t a=bits(actual), b=bits(reference);
        result.bit_differences+=a!=b;
        if (!finite_bits(a) || !finite_bits(b)) {
            ++result.errors; result.max_ulp=UINT32_MAX;
            // Exact diagnostic encodings: +infinity; never silently hide NaNs.
            const uint32_t infinity=0x7f800000u;
            std::memcpy(&result.max_abs, &infinity, sizeof(infinity));
            std::memcpy(&result.max_rel, &infinity, sizeof(infinity));
            continue;
        }
        const float absolute=std::fabs(actual-reference), magnitude=std::fabs(reference);
        const float relative=absolute/(magnitude>1.0e-12f ? magnitude : 1.0e-12f);
        if (absolute>result.max_abs) result.max_abs=absolute;
        if (relative>result.max_rel) result.max_rel=relative;
        const unsigned ulp=ulp_distance(actual, reference);
        if (ulp>result.max_ulp) result.max_ulp=ulp;
        result.errors+=absolute>Atol+Rtol*magnitude;
    }
    return result;
}

int main() {
    const float *inputs[Stages]={decode_input_0,decode_input_1,decode_input_2,decode_input_3};
    const unsigned char *packed[Stages]={decode_quantized_0,decode_quantized_1,decode_quantized_2,decode_quantized_3};
    const unsigned char *weights[Parts]={decode_weights_0,decode_weights_1,decode_weights_2,decode_weights_3,
        decode_weights_4,decode_weights_5,decode_weights_6};
    const float *expected[Parts]={decode_expected_0,decode_expected_1,decode_expected_2,decode_expected_3,
        decode_expected_4,decode_expected_5,decode_expected_6};
    unsigned long vlenb;
    asm volatile("csrr %0,vlenb" : "=r"(vlenb));
    if (vlenb!=128) {
        printf("RVV_DECODE_FAIL reason=vlenb actual=%lu expected=128\n", vlenb); return 1;
    }
    for (unsigned part=0; part<Parts; ++part) {
        if (decode_profiles[part]!=Profiles[part]) {
            printf("RVV_DECODE_FAIL reason=profile part=%u actual=%u expected=%u\n",
                   part,decode_profiles[part],Profiles[part]); return 1;
        }
    }
    std::memset(activation,0xa5,sizeof(activation)); std::memset(output,0xa5,sizeof(output));
    uint64_t prep[Stages]{}, dispatch[Parts]{}, execution[Parts]{};
    State prep_before[Stages]{}, prep_after[Stages]{}, dispatch_before[Parts]{}, before[Parts]{}, after[Parts]{};
    asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
    printf("RVV_DECODE_SCOPE m=1 n=128 parts=7 stages=4 trials=1 full_k=1 full_n=0 full_ggml=0 "
           "q4_layout=r32 q6_layout=row_major atol=2e-3 rtol=2e-3 reference=existing_expected independent_rvv_oracle=0\n");
    const uint64_t begin=cycle();
    // Same production order as Decode: Q, V, K, gate, up, down, captured vocab.
    for (unsigned part=0; part<Parts; ++part) {
        const unsigned stage=PartStage[part];
        if (part==0 || part==3 || part==5 || part==6) {
            prep_before[stage]=state();
            const uint64_t start=cycle();
            quantize_row_q8_K(inputs[stage],activation[stage]+64,PartK[part]);
            prep[stage]=cycle()-start; prep_after[stage]=state();
        }
        Dispatch d;
        dispatch_before[part]=state();
        const uint64_t d0=cycle();
        prepare_dispatch(part, weights[part], &d);
        const uint64_t d1=cycle();
        before[part]=state();
        const uint64_t e0=cycle();
        execute_dispatch(&d);
        const uint64_t e1=cycle();
        after[part]=state();
        dispatch[part]=d1-d0; execution[part]=e1-e0;
    }
    const uint64_t end=cycle();

    // All validation, checksums, diagnostics and output dumping are untimed.
    unsigned errors=0, q4_calls=0, q6_calls=0;
    uint64_t prep_sum=0, dispatch_sum=0, execute_sum=0;
    for (unsigned stage=0; stage<Stages; ++stage) {
        const size_t bytes=(stage==2 ? 24u : 8u)*Q8Bytes;
        const unsigned payload_errors=std::memcmp(activation[stage]+64,packed[stage],bytes)!=0;
        unsigned guard_errors=0;
        for (unsigned i=0; i<64; ++i) guard_errors+=activation[stage][i]!=0xa5;
        for (size_t i=64+bytes; i<sizeof(activation[stage]); ++i) guard_errors+=activation[stage][i]!=0xa5;
        const unsigned state_errors=!fp_state_preserved(prep_before[stage],prep_after[stage]) ||
            prep_before[stage].vc!=(stage==0 ? 5u : 3u) || prep_after[stage].vc!=3u;
        errors+=payload_errors+guard_errors+state_errors+(prep[stage]==0);
        prep_sum+=prep[stage];
        printf("RVV_DECODE_PREP stage=%u k=%u cycles=%lu before_fcsr=%u fcsr=%u before_vcsr=%u vcsr=%u "
               "before_vstart=%u vstart=%u checksum=%u payload_errors=%u guard_errors=%u state_errors=%u\n",
               stage,stage==2 ? 6144u : 2048u,(unsigned long)prep[stage],prep_before[stage].fc,prep_after[stage].fc,
               prep_before[stage].vc,prep_after[stage].vc,prep_before[stage].vs,prep_after[stage].vs,
               checksum(activation[stage]+64,bytes),payload_errors,guard_errors,state_errors);
    }
    for (unsigned part=0; part<Parts; ++part) {
        const Metrics metrics=compare(part,expected[part]);
        const auto *raw=reinterpret_cast<const unsigned char *>(output[part]);
        unsigned guard_errors=0;
        for (unsigned i=0; i<64; ++i) guard_errors+=raw[i]!=0xa5 || raw[64+N*sizeof(float)+i]!=0xa5;
        const unsigned state_errors=!same_state(dispatch_before[part],before[part]) ||
            !fp_state_preserved(before[part],after[part]) || before[part].vc!=3u || after[part].vc!=3u;
        const unsigned local=metrics.errors+guard_errors+state_errors+(dispatch[part]==0)+(execution[part]==0);
        errors+=local; dispatch_sum+=dispatch[part]; execute_sum+=execution[part];
        const unsigned calls=Profiles[part]==1 ? 1u : N;
        if (Profiles[part]==1) q4_calls+=calls; else q6_calls+=calls;
        printf("RVV_DECODE_PART part=%u profile=%u k=%u stage=%u dispatch=%lu execution=%lu calls=%u "
               "before_fcsr=%u fcsr=%u before_vcsr=%u vcsr=%u before_vstart=%u vstart=%u checksum=%u "
               "bit_differences=%u max_abs_bits=%u max_rel_bits=%u max_ulp=%u mismatches=%u "
               "guard_errors=%u state_errors=%u errors=%u\n",
               part,Profiles[part],PartK[part],PartStage[part],(unsigned long)dispatch[part],(unsigned long)execution[part],calls,
               before[part].fc,after[part].fc,before[part].vc,after[part].vc,before[part].vs,after[part].vs,
               checksum(output[part]+16,N*sizeof(float)),metrics.bit_differences,bits(metrics.max_abs),bits(metrics.max_rel),
               metrics.max_ulp,metrics.errors,guard_errors,state_errors,local);
        for (unsigned idx=0; idx<N; ++idx)
            printf("RVV_DECODE_OUTPUT part=%u idx=%u bits=%u\n",part,idx,bits(output[part][16+idx]));
    }
    errors+=q4_calls!=4 || q6_calls!=384 || end-begin<prep_sum+dispatch_sum+execute_sum;
    printf("RVV_DECODE_RESULT preparation=%lu dispatch=%lu execution=%lu region=%lu parts=7 outputs=896 "
           "q4_calls=%u q6_calls=%u errors=%u\n",(unsigned long)prep_sum,(unsigned long)dispatch_sum,
           (unsigned long)execute_sum,(unsigned long)(end-begin),q4_calls,q6_calls,errors);
    return errors ? 1 : 0;
}
