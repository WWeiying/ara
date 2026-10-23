#include "ggml_m4_prepare_candidate.h"
#include "printf.h"
#include "golden_state.h"

extern "C" const float m4_capture[];
extern "C" const unsigned char m4_golden[];
alignas(64) static block_q8_0x4 reference[28];
alignas(64) static block_q8_0x4 output[28];

static unsigned fpstate() {
    unsigned value;
    asm volatile("frcsr %0" : "=r"(value) : : "memory");
    return value;
}

static uint64_t cycle() {
    uint64_t value;
    asm volatile("fence rw, rw; rdcycle %0" : "=r"(value) : : "memory");
    return value;
}

__attribute__((noinline)) static bool vector_prepare(void * target) {
    return qbs_m4_prepare_candidate::quantize(m4_capture, target, 896);
}

int main() {
    // One real activation group, four calls, order ABBA. No printing in timing.
    uint64_t cycles[4];
    unsigned observed_flags[4];
    const bool vector_path[4] = {false, true, true, false};
    bool used[4] = {};
    unsigned errors = 0;
    for (int trial = 0; trial < 4; ++trial) {
        std::memset(output, 0xa5, sizeof(output));
        asm volatile("fscsr zero; csrwi vcsr, 5" ::: "memory");
        const uint64_t begin = cycle();
        if (vector_path[trial]) used[trial] = vector_prepare(output);
        else ggml_quantize_mat_q8_0_4x1_generic(m4_capture, output, 896);
        // CSR visibility drains vector FP operations; fence drains output writes.
        observed_flags[trial] = fpstate();
        cycles[trial] = cycle() - begin;
        unsigned vcsr;
        asm volatile("csrr %0, vcsr" : "=r"(vcsr) : : "memory");
        errors += vcsr != 5 || observed_flags[trial] != M4_GOLDEN_FCSR;
        const auto * actual_bytes = reinterpret_cast<const unsigned char *>(output);
        for (size_t j = 0; j < sizeof(output); ++j) errors += actual_bytes[j] != m4_golden[j];
        if (trial == 0) std::memcpy(reference, output, sizeof(reference));
        else {
            const auto * actual = reinterpret_cast<const unsigned char *>(output);
            const auto * expected = reinterpret_cast<const unsigned char *>(reference);
            for (size_t j = 0; j < sizeof(output); ++j) errors += actual[j] != expected[j];
            errors += observed_flags[trial] != observed_flags[0];
        }
        errors += used[trial] != vector_path[trial];
    }
    for (int trial = 0; trial < 4; ++trial) {
        printf("M4_SOC trial=%d path=%s cycles=%lu flags=%u used=%d\n", trial,
               vector_path[trial] ? "vector" : "generic", (unsigned long)cycles[trial],
               observed_flags[trial], (int)used[trial]);
    }
    printf("M4_SOC_RESULT errors=%u bytes=%lu inputs=3584 k=896 calls=4 golden=linux_ggml\n",
           errors, (unsigned long)sizeof(output));
    return errors ? 1 : 0;
}
