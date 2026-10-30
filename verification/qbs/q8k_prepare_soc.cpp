#include "ggml_q8k_m4_prepare_candidate.h"
#include "printf.h"
#include "golden_state.h"

extern "C" const float q8k_capture[];
extern "C" const unsigned char q8k_golden[];
alignas(64) static block_q8_Kx4 output[8];

static uint64_t cycle() {
    uint64_t c;
    asm volatile("fence rw, rw; rdcycle %0" : "=r"(c) : : "memory");
    return c;
}

__attribute__((noinline)) static bool prepare(void * target) {
    return qbs_q8k_m4_prepare_candidate::quantize(q8k_capture, target, 1536);
}

int main() {
    uint64_t elapsed[4];
    unsigned flags[4], errors = 0;
    const bool vector[4] = {false, true, true, false};
    bool used[4] = {};
    for (int t = 0; t < 4; ++t) {
        std::memset(output, 0xa5, sizeof(output));
        asm volatile("fscsr zero; csrwi vcsr, 5" ::: "memory");
        const uint64_t begin = cycle();
        if (vector[t]) used[t] = prepare(output + 1);
        else ggml_quantize_mat_q8_K_4x1_ara_generic(q8k_capture, output + 1, 1536);
        asm volatile("frcsr %0" : "=r"(flags[t]) : : "memory");
        elapsed[t] = cycle() - begin;
        unsigned vcsr;
        asm volatile("csrr %0, vcsr" : "=r"(vcsr) : : "memory");
        errors += flags[t] != Q8K_GOLDEN_FCSR || vcsr != 5 || used[t] != vector[t];
        const auto * bytes = reinterpret_cast<const unsigned char *>(output + 1);
        for (size_t j = 0; j < 7008; ++j) errors += bytes[j] != q8k_golden[j];
        for (int g = 0; g < 2; ++g) {
            const auto * guard = reinterpret_cast<const unsigned char *>(&output[g ? 7 : 0]);
            for (size_t j = 0; j < sizeof(output[0]); ++j) errors += guard[j] != 0xa5;
        }
    }
    for (int t = 0; t < 4; ++t)
        printf("Q8K_SOC trial=%d path=%s cycles=%lu flags=%u used=%d\n", t,
               vector[t] ? "vector" : "generic", (unsigned long)elapsed[t], flags[t], int(used[t]));
    printf("Q8K_SOC_RESULT errors=%u bytes=7008 inputs=6144 k=1536 calls=4 golden=linux_ggml\n", errors);
    return errors ? 1 : 0;
}
