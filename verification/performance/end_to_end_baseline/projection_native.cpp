#include "qbs/qbs.h"
#include "q8_K-m4-packed.h"
#include "printf.h"
#include <cmath>
#include <cstring>

extern "C" const float projection_input[], q_expected[], k_expected[], v_expected[];
extern "C" const unsigned char projection_golden[], q_weights[], k_weights[], v_weights[];
extern "C" const unsigned q_flags[], k_flags[], v_flags[];
enum : unsigned { K=2048, N=128, M=4, Packed=8*4*QBS_Q8_K_BLOCK_BYTES };
alignas(64) static unsigned char activation[Packed+128];
alignas(64) static float output[3][M*N+32];
static unsigned commands = 0;
static uint64_t cycle() { uint64_t x; asm volatile("fence rw,rw;rdcycle %0" : "=r"(x) :: "memory"); return x; }
static unsigned fcsr() { unsigned x; asm volatile("frcsr %0" : "=r"(x) :: "memory"); return x; }
static unsigned vcsr() { unsigned x; asm volatile("csrr %0,vcsr" : "=r"(x) :: "memory"); return x; }
static unsigned checksum(const void *data, size_t bytes) {
    auto *p = static_cast<const unsigned char *>(data); unsigned hash = 2166136261u;
    for (size_t i = 0; i < bytes; ++i) hash = (hash ^ p[i])*16777619u;
    return hash;
}
static qbs_status_t execute(void *, const qbs_descriptor_t *d, unsigned m, const void *a,
                            float *o, size_t stride, unsigned n, int segmented) {
    ++commands;
    return qbs_native_execute_command(nullptr, d, m, a, o, stride, n, segmented);
}
int main() {
    qbs_device_t device{};
    if (qbs_device_query(qbs_native_info, nullptr, &device) != QBS_STATUS_OK) {
        printf("MATRIX_NATIVE_FAIL reason=device\n"); return 1;
    }
    const unsigned char *weights[] = {q_weights, k_weights, v_weights};
    const float *expected[] = {q_expected, k_expected, v_expected};
    const unsigned *flags[] = {q_flags, k_flags, v_flags};
    const unsigned profiles[] = {QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q6_K};
    const size_t bytes[] = {128*8*144, 128*8*144, 128*8*210};
    unsigned total_errors = 0;
    printf("MATRIX_NATIVE_SCOPE model=qwen3_1p7b layer=0 source=attn_norm-0 m=4 n=128 k=2048 parts=3 trials=2 full_ggml=0\n");
    for (unsigned trial = 0; trial < 2; ++trial) {
        std::memset(activation, 0xa5, sizeof(activation));
        std::memset(output, 0xa5, sizeof(output));
        asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
        commands = 0;
        const uint64_t begin = cycle();
        const bool vector_prepared = ggml_riscv_q8_K_m4_packed::quantize<true>(projection_input, activation+64, K);
        const uint64_t prepared = cycle();
        const unsigned preparation_flags = fcsr();
        uint64_t admission = 0, execution = 0;
        uint64_t admit_part[3], execute_part[3];
        unsigned observed_fc[3], observed_vc[3];
        unsigned local_errors = !vector_prepared;
        for (unsigned part = 0; part < 3; ++part) {
            qbs_problem_t problem = {static_cast<uint8_t>(profiles[part]), QBS_ACTIVATION_PROFILE_Q8_K,
                QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, QBS_ACTIVATION_STORAGE_M4_GROUPED, M, N, K};
            qbs_plan_t plan{};
            const uint64_t a = cycle();
            const auto admitted = qbs_plan_create(&device, &problem, &plan);
            const uint64_t b = cycle();
            const auto status = admitted == QBS_STATUS_OK ?
                qbs_execute(&plan, weights[part], bytes[part], activation+64, Packed,
                            output[part]+16, M*N, N, nullptr, 0, execute, nullptr) : admitted;
            const uint64_t c = cycle();
            admission += b-a; execution += c-b;
            admit_part[part] = b-a; execute_part[part] = c-b;
            observed_fc[part] = fcsr(); observed_vc[part] = vcsr();
            local_errors += admitted != QBS_STATUS_OK || status != QBS_STATUS_OK ||
                plan.command_m != M || plan.command_n != 32 || plan.k_blocks != 8 ||
                plan.split_k || plan.uses_wide_m || qbs_plan_supports_activation_context(&plan);
        }
        const uint64_t end = cycle();
        for (unsigned part = 0; part < 3; ++part) {
            unsigned errors = std::memcmp(output[part]+16, expected[part], M*N*sizeof(float)) != 0;
            for (unsigned i = 0; i < M*N; ++i) errors += !std::isfinite(output[part][16+i]);
            const unsigned char *raw = reinterpret_cast<const unsigned char *>(output[part]);
            for (unsigned i = 0; i < 64; ++i) errors += raw[i] != 0xa5 || raw[64+M*N*4+i] != 0xa5;
            // Final flags accumulate across the three blocking calls.
            unsigned wanted = preparation_flags;
            for (unsigned p = 0; p <= part; ++p) wanted |= *flags[p];
            errors += observed_fc[part] != wanted || observed_vc[part] != 5;
            local_errors += errors;
            printf("MATRIX_NATIVE_PART trial=%u part=%u profile=%u admission=%lu execution=%lu fcsr=%u vcsr=%u checksum=%u errors=%u\n",
                trial, part, profiles[part], (unsigned long)admit_part[part], (unsigned long)execute_part[part],
                observed_fc[part], observed_vc[part], checksum(output[part]+16, M*N*sizeof(float)), errors);
        }
        local_errors += std::memcmp(activation+64, projection_golden, Packed) != 0 || commands != 12;
        for (unsigned i = 0; i < 64; ++i)
            local_errors += activation[i] != 0xa5 || activation[64+Packed+i] != 0xa5;
        total_errors += local_errors;
        printf("MATRIX_NATIVE_TRIAL id=%u preparation=%lu admission=%lu execution=%lu region=%lu commands=%u errors=%u\n",
            trial, (unsigned long)(prepared-begin), (unsigned long)admission, (unsigned long)execution,
            (unsigned long)(end-begin), commands, local_errors);
    }
    printf("MATRIX_NATIVE_RESULT trials=2 commands=24 outputs=3072 errors=%u\n", total_errors);
    return total_errors ? 1 : 0;
}
