#include "ggml_q8k_m4_prepare_candidate.h"
#include "qbs/qbs.h"
#include "printf.h"
#include "golden_state.h"

extern "C" const float projection_input[];
extern "C" const unsigned char projection_weights[];
extern "C" const unsigned char projection_packed_golden[];
extern "C" const float projection_oracle[];
alignas(64) static block_q8_Kx4 packed[8];
alignas(64) static float output[6144 + 32];

static uint64_t cycle() {
    uint64_t c;
    asm volatile("fence rw, rw; rdcycle %0" : "=r"(c) : : "memory");
    return c;
}

static unsigned fcsr() {
    unsigned value;
    asm volatile("frcsr %0" : "=r"(value) : : "memory");
    return value;
}

__attribute__((noinline)) static bool prepare() {
    return qbs_q8k_m4_prepare_candidate::quantize(projection_input, packed + 1, 1536);
}

__attribute__((noinline)) static qbs_status_t project() {
    for (unsigned first = 0; first < 1536; first += 32) {
        qbs_descriptor_fields_t fields = {};
        fields.descriptor_version = QBS_DESCRIPTOR_VERSION;
        fields.weight_profile = QBS_WEIGHT_PROFILE_Q4_K;
        fields.activation_profile = QBS_ACTIVATION_PROFILE_Q8_K;
        fields.weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
        fields.activation_layout = QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED;
        fields.n = 32;
        fields.k_blocks = 6;
        fields.activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
        const qbs_descriptor_t descriptor = {
            qbs_pack_descriptor_header(&fields),
            reinterpret_cast<uintptr_t>(projection_weights + first * 6 * 144)
        };
        const auto status = qbs_native_execute_command(nullptr, &descriptor, 4,
            packed + 1, output + 16 + first, 1536, 32, 0);
        if (status != QBS_STATUS_OK) return status;
    }
    return QBS_STATUS_OK;
}

int main() {
    const bool vector[4] = {false, true, true, false};
    uint64_t prep_cycles[4], matmul_cycles[4], checksums[4];
    unsigned flags[4], errors = 0;
    bool used[4] = {};
    for (int trial = 0; trial < 4; ++trial) {
        std::memset(packed, 0xa5, sizeof(packed));
        std::memset(output, 0xa5, sizeof(output));
        asm volatile("fscsr zero; csrwi vcsr, 5" ::: "memory");
        const uint64_t begin = cycle();
        if (vector[trial]) used[trial] = prepare();
        else ggml_quantize_mat_q8_K_4x1_ara_generic(projection_input, packed + 1, 1536);
        const unsigned prep_flags = fcsr();
        const uint64_t midpoint = cycle();
        const auto status = project();
        flags[trial] = fcsr();
        matmul_cycles[trial] = cycle() - midpoint;
        prep_cycles[trial] = midpoint - begin;
        unsigned vcsr;
        asm volatile("csrr %0, vcsr" : "=r"(vcsr) : : "memory");
        errors += status != QBS_STATUS_OK || prep_flags != Q8K_GOLDEN_FCSR ||
                  vcsr != 5 || used[trial] != vector[trial];
        const auto * bytes = reinterpret_cast<const unsigned char *>(packed + 1);
        for (size_t j = 0; j < 7008; ++j) errors += bytes[j] != projection_packed_golden[j];
        for (unsigned g = 0; g < 2; ++g) {
            const auto * guard = reinterpret_cast<const unsigned char *>(&packed[g ? 7 : 0]);
            for (size_t j = 0; j < sizeof(packed[0]); ++j) errors += guard[j] != 0xa5;
            guard = reinterpret_cast<const unsigned char *>(output + (g ? 6160 : 0));
            for (size_t j = 0; j < 16*sizeof(float); ++j) errors += guard[j] != 0xa5;
        }
        uint64_t hash = UINT64_C(14695981039346656037);
        for (unsigned i = 0; i < 6144; ++i) {
            const float actual = output[16+i], expected = projection_oracle[i];
            errors += !std::isfinite(actual) || !std::isfinite(expected) ||
                      fabsf(actual - expected) > 2e-4f + 2e-5f * fabsf(expected);
            uint32_t bits;
            std::memcpy(&bits, &actual, sizeof(bits));
            for (unsigned b = 0; b < 4; ++b) hash = (hash ^ ((bits >> (8*b)) & 255)) * UINT64_C(1099511628211);
        }
        checksums[trial] = hash;
        if (trial) errors += hash != checksums[0] || flags[trial] != flags[0];
    }
    for (int t = 0; t < 4; ++t)
        printf("Q8K_PROJECTION trial=%d path=%s prep=%lu matmul=%lu total=%lu flags=%u checksum=%016lx\n",
               t, vector[t] ? "vector" : "generic", (unsigned long)prep_cycles[t],
               (unsigned long)matmul_cycles[t], (unsigned long)(prep_cycles[t]+matmul_cycles[t]),
               flags[t], (unsigned long)checksums[t]);
    printf("Q8K_PROJECTION_RESULT errors=%u m=4 n=1536 k=1536 outputs=6144 calls=4 commands=192 golden=independent\n", errors);
    return errors ? 1 : 0;
}
